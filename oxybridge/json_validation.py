"""Bound JSON Schema regex work and error collection at the workflow boundary."""

import json
import time
from contextvars import ContextVar
from itertools import islice

import regex
from jsonschema import Draft202012Validator, ValidationError, validators

deadline = ContextVar("json_validation_deadline", default=float("inf"))


def match(pattern, value):
    remaining = deadline.get() - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("JSON Schema validation exceeded its budget")
    return regex.search(pattern, value, timeout=min(0.05, remaining))


def pattern(validator, value, instance, schema):
    if validator.is_type(instance, "string") and not match(value, instance):
        yield ValidationError("The string does not match the pattern")


def pattern_properties(validator, value, instance, schema):
    if validator.is_type(instance, "object"):
        for expression, subschema in value.items():
            for key, item in instance.items():
                if match(expression, key):
                    yield from validator.descend(item, subschema, path=key, schema_path=expression)


def additional_properties(validator, value, instance, schema):
    if not validator.is_type(instance, "object"):
        return
    for key in instance:
        if key in schema.get("properties", {}) or any(
            match(expression, key) for expression in schema.get("patternProperties", {})
        ):
            continue
        if validator.is_type(value, "object"):
            yield from validator.descend(instance[key], value, path=key)
        elif not value:
            yield ValidationError("Additional properties are not allowed")


def identity(value):
    if isinstance(value, dict):
        return ("object", tuple((key, identity(item)) for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ("array", tuple(identity(item) for item in value))
    return (
        "boolean"
        if isinstance(value, bool)
        else "number"
        if isinstance(value, (int, float))
        else type(value).__name__,
        value,
    )


def unique_items(validator, value, instance, schema):
    if value and validator.is_type(instance, "array"):
        seen = set()
        for item in instance:
            if time.monotonic() >= deadline.get():
                raise TimeoutError("JSON Schema validation exceeded its budget")
            key = identity(item)
            if key in seen:
                yield ValidationError("Array items must be unique")
                return
            seen.add(key)


def bounded(function):
    def check(validator, value, instance, schema):
        if time.monotonic() >= deadline.get():
            raise TimeoutError("JSON Schema validation exceeded its budget")
        yield from function(validator, value, instance, schema)
        if time.monotonic() >= deadline.get():
            raise TimeoutError("JSON Schema validation exceeded its budget")

    return check


SafeValidator = validators.extend(
    Draft202012Validator,
    {
        key: bounded(function)
        for key, function in {
            **Draft202012Validator.VALIDATORS,
            "pattern": pattern,
            "patternProperties": pattern_properties,
            "additionalProperties": additional_properties,
            "uniqueItems": unique_items,
        }.items()
    },
)


def check_schema(schema):
    # Nested draft switches could bypass the bounded validator during descend().
    nested = {key: value for key, value in schema.items() if key != "$schema"}
    text = json.dumps(nested)
    if (
        '"$schema"' in text
        or schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        raise ValueError("Use JSON Schema draft 2020-12; declare the draft only at the root")
    if '"patternProperties"' in text and '"unevaluatedProperties"' in text:
        # shortcut: this combination is rejected; enable after bounded evaluated-property tracking.
        raise ValueError(
            "Use additionalProperties with patternProperties instead of unevaluatedProperties"
        )
    Draft202012Validator.check_schema(schema)


def errors(schema, value):
    check_schema(schema)
    token = deadline.set(time.monotonic() + 1)
    try:
        return list(islice(SafeValidator(schema).iter_errors(value), 20))
    finally:
        deadline.reset(token)
