import pytest

from oxybridge.graph import NodeError
from oxybridge.json_validation import check_schema, errors
from oxybridge.nodes import execute_node


@pytest.mark.parametrize(
    "schema,value",
    [
        ({"pattern": "(a+)+$"}, "a" * 50000 + "!"),
        ({"patternProperties": {"(a+)+$": {"type": "string"}}}, {"a" * 50000 + "!": "value"}),
        (
            {"additionalProperties": False, "patternProperties": {"(a+)+$": {}}},
            {"a" * 50000 + "!": "value"},
        ),
    ],
    ids=["pattern", "pattern-properties", "additional-properties"],
)
def test_schema_regex_exhaustion_is_a_bounded_node_failure(schema, value):
    with pytest.raises(NodeError) as error:
        execute_node(
            {"type": "validate", "config": {"schema": schema}}, {"trigger": {"body": value}}
        )
    assert error.value.code == "VALIDATION_LIMIT"
    assert not error.value.retryable


def test_pattern_properties_and_additional_property_schema_keep_their_semantics():
    schema = {
        "properties": {"fixed": {"type": "boolean"}},
        "patternProperties": {"^num_": {"type": "number"}},
        "additionalProperties": {"type": "string"},
    }
    assert errors(schema, {"fixed": True, "num_one": 1, "label": "okay"}) == []
    assert {e.validator for e in errors(schema, {"num_one": "wrong", "label": 1})} == {"type"}
    assert errors({"pattern": "^a+$"}, "aaa") == []
    assert errors({"pattern": "^a+$"}, "b")[0].validator == "pattern"


def test_unique_items_preserves_json_type_and_numeric_equality():
    schema = {"uniqueItems": True}
    assert errors(schema, [True, 1, {"x": [1, "a"]}, {"x": [2, "a"]}]) == []
    assert errors(schema, [{"x": 1}, {"x": 1.0}])[0].validator == "uniqueItems"
    assert errors(schema, [{"id": i} for i in range(10000)]) == []


def test_nested_draft_changes_cannot_bypass_bounded_validation():
    with pytest.raises(ValueError):
        check_schema(
            {"properties": {"x": {"$schema": "https://json-schema.org/draft/2020-12/schema"}}}
        )
    with pytest.raises(ValueError):
        check_schema({"patternProperties": {"(a+)+$": {}}, "unevaluatedProperties": False})
    with pytest.raises(NodeError) as error:
        execute_node(
            {
                "type": "validate",
                "config": {
                    "schema": {"patternProperties": {"(a+)+$": {}}, "unevaluatedProperties": False}
                },
            },
            {"trigger": {"body": {}}},
        )
    assert error.value.code == "NODE_CONFIG_INVALID"
    check_schema(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "properties": {"x": {"pattern": "^a+$"}},
        }
    )


def test_validation_error_collection_is_bounded():
    assert len(errors({"items": {"type": "number"}}, ["bad"] * 10000)) == 20
