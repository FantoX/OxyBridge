import json
import re
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import regex
from croniter import croniter

from oxybridge.json_validation import check_schema
from oxybridge.security import connection_references

TRIGGERS = {"manual", "webhook", "schedule", "api"}
TYPES = TRIGGERS | {
    "http",
    "callback",
    "postgres",
    "transform",
    "condition",
    "validate",
    "set",
    "delay",
}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}
NODE_TERMINAL = {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED"}
EXPRESSION = re.compile(r"{{\s*([^{}]+?)\s*}}")
PATH = re.compile(r"^(?:trigger|nodes|env|run|vars)(?:\.[A-Za-z0-9_-]+)*$")


class NodeError(Exception):
    def __init__(self, code, message, retryable=False, http_status=None):
        super().__init__(message)
        self.code, self.retryable, self.http_status = code, retryable, http_status


def lookup(context, path):
    if not PATH.fullmatch(path) or any(p.startswith("__") for p in path.split(".")):
        raise NodeError(
            "EXPRESSION_FAILED", "Use a dot path within trigger, nodes, env, run or vars."
        )
    current = context
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            raise NodeError("EXPRESSION_FAILED", f"The expression path '{path}' is unavailable.")
    return current


def resolve(value, context):
    if isinstance(value, dict):
        return {k: resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    if not isinstance(value, str):
        return value
    match = EXPRESSION.fullmatch(value.strip())
    if match:
        return lookup(context, match[1].strip())
    return EXPRESSION.sub(lambda m: str(lookup(context, m[1].strip())), value)


def condition(config, context, depth=0):
    if depth > 8:
        raise NodeError("NODE_CONFIG_INVALID", "Condition groups exceed the nesting limit.")
    if "rules" in config:
        results = [condition(rule, context, depth + 1) for rule in config["rules"]]
        return all(results) if config.get("mode", "AND") == "AND" else any(results)
    operation = config.get("operator", "equals")
    try:
        left = resolve(config.get("left"), context)
    except NodeError:
        if operation == "exists":
            return False
        raise
    right = resolve(config.get("right"), context)
    try:
        match operation:
            case "equals":
                return left == right
            case "not_equals":
                return left != right
            case "exists":
                return left is not None
            case "contains":
                return right in left
            case "greater":
                return float(left) > float(right)
            case "less":
                return float(left) < float(right)
            case "regex":
                return bool(regex.search(str(right), str(left)[:10000], timeout=0.05))
    except (TypeError, ValueError, TimeoutError, regex.error) as error:
        raise NodeError(
            "NODE_CONFIG_INVALID", "Condition values or pattern are invalid."
        ) from error
    raise NodeError("NODE_CONFIG_INVALID", "Unsupported condition operator.")


def next_times(cron, timezone, start, count=5):
    if len(cron.split()) != 5:
        raise ValueError("Use a five-field cron expression")
    iterator = croniter(cron, start.astimezone(ZoneInfo(timezone)), max_years_between_matches=2)
    return [iterator.get_next(type(start)) for _ in range(count)]


def validate(definition, connections=None):
    errors = []

    def issue(message, node_id=None, field=None, code="NODE_CONFIG_INVALID"):
        errors.append({"code": code, "message": message, "node_id": node_id, "field": field})

    if not isinstance(definition, dict) or definition.get("schema_version") != 1:
        issue("Use workflow schema version 1.", code="WORKFLOW_INVALID")
        return {"valid": False, "errors": errors, "warnings": []}
    nodes, edges = definition.get("nodes", []), definition.get("edges", [])
    if (
        not isinstance(nodes, list)
        or not isinstance(edges, list)
        or len(nodes) > 200
        or len(edges) > 400
    ):
        issue("A workflow supports up to 200 nodes and 400 edges.")
        return {"valid": False, "errors": errors, "warnings": []}
    if not nodes or any(not isinstance(n, dict) for n in nodes + edges):
        issue("Add a trigger and at least one node.")
        return {"valid": False, "errors": errors, "warnings": []}
    ids = [n.get("id") for n in nodes]
    if any(not isinstance(i, str) for i in ids):
        issue("Every node needs a UUID.")
        return {"valid": False, "errors": errors, "warnings": []}
    if len(set(ids)) != len(ids):
        issue("Node IDs must be unique.")
    by_id = {n["id"]: n for n in nodes}
    edge_ids = set()
    incoming, outgoing = {i: [] for i in ids}, {i: [] for i in ids}
    for edge in edges:
        try:
            UUID(edge.get("id", ""))
        except (ValueError, TypeError, AttributeError):
            issue("Every edge needs a UUID.")
        if edge.get("id") in edge_ids:
            issue("Edge IDs must be unique.")
        edge_ids.add(edge.get("id"))
        source, target = edge.get("source"), edge.get("target")
        if source not in by_id or target not in by_id:
            issue("An edge references a missing node.")
            continue
        incoming[target].append(source)
        outgoing[source].append(target)
        kind = by_id[source].get("type")
        allowed = (
            {"true", "false"}
            if kind == "condition"
            else {"valid", "invalid"}
            if kind == "validate"
            else {"success", None}
        )
        if edge.get("sourceHandle") not in allowed:
            issue("Select a supported output handle.", source)
    triggers = [n for n in nodes if n.get("type") in TRIGGERS]
    if len(triggers) != 1:
        issue("A workflow must have exactly one trigger.")
    for trigger in triggers:
        if incoming[trigger["id"]]:
            issue("Triggers cannot have incoming connections.", trigger["id"])
    remaining = {i: len(incoming[i]) for i in ids}
    ready = [i for i in ids if remaining[i] == 0]
    ordered = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in outgoing[current]:
            remaining[target] -= 1
            if remaining[target] == 0:
                ready.append(target)
    if len(ordered) != len(by_id):
        issue("Workflow cycles are not supported.", code="WORKFLOW_INVALID")
    reachable = set()
    pending = [n["id"] for n in triggers]
    while pending:
        current = pending.pop()
        if current not in reachable:
            reachable.add(current)
            pending.extend(outgoing[current])
    for node in nodes:
        node_id, kind, config = node["id"], node.get("type"), node.get("config", {})
        try:
            UUID(node_id)
        except ValueError:
            issue("Node IDs must be UUIDs.", node_id)
        if node_id not in reachable:
            issue("Connect this node to the trigger.", node_id)
        if kind not in TYPES or not isinstance(config, dict):
            issue("Unsupported node type or configuration.", node_id)
            continue
        if not isinstance(node.get("label", ""), str) or len(node.get("label", "")) > 120:
            issue("Node names must be at most 120 characters.", node_id)
        try:
            connection_references(config)
            if kind in {"http", "callback"}:
                url = config.get("url", "")
                parts = urlsplit(EXPRESSION.sub("placeholder", url))
                if (
                    parts.scheme not in {"http", "https"}
                    or not parts.hostname
                    or parts.username
                    or parts.password
                ):
                    raise ValueError("Enter an HTTP(S) URL without embedded credentials.")
                if config.get("method", "POST" if kind == "callback" else "GET") not in {
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                }:
                    raise ValueError("Unsupported HTTP method.")
                if not 0 < float(config.get("timeout", 30)) <= 120:
                    raise ValueError("Timeout must be between 0 and 120 seconds.")
                if not isinstance(config.get("headers", {}), dict) or not isinstance(
                    config.get("query", {}), dict
                ):
                    raise ValueError("Headers and query parameters must be JSON objects.")
            if kind == "postgres":
                if not config.get("connection_id") or not config.get("query"):
                    raise ValueError("Select a PostgreSQL connection and enter a query.")
                if "{{" in config["query"] or ";" in config["query"].rstrip().rstrip(";"):
                    raise ValueError(
                        "Use one parameterized query; expressions belong in parameters."
                    )
                if config.get("mode", "read") not in {"read", "write"}:
                    raise ValueError("Select read or write mode.")
            if kind == "validate":
                schema = config.get("schema")
                if not isinstance(schema, dict) or "$ref" in json.dumps(schema):
                    raise ValueError(
                        "Provide a self-contained JSON Schema without external references."
                    )
                check_schema(schema)
            if kind in {"transform", "set"} and not isinstance(config.get("mapping"), dict):
                raise ValueError("Provide a JSON object mapping.")
            if kind == "condition":

                def check_rule(rule, depth=0):
                    if depth > 8 or not isinstance(rule, dict):
                        raise ValueError("Invalid condition group.")
                    if "rules" in rule:
                        if (
                            rule.get("mode", "AND") not in {"AND", "OR"}
                            or not isinstance(rule["rules"], list)
                            or not 1 <= len(rule["rules"]) <= 20
                        ):
                            raise ValueError("Condition groups need 1–20 rules and AND/OR mode.")
                        for child in rule["rules"]:
                            check_rule(child, depth + 1)
                    elif (
                        rule.get("operator")
                        not in {
                            "equals",
                            "not_equals",
                            "contains",
                            "exists",
                            "greater",
                            "less",
                            "regex",
                        }
                        or "left" not in rule
                    ):
                        raise ValueError("Choose a condition operator and left value.")

                check_rule(config)
            if kind == "schedule":
                from oxybridge.db import now

                next_times(config.get("cron", ""), config.get("timezone", ""), now())
            if kind == "delay" and not 0 <= float(config.get("seconds", -1)) <= 86400:
                raise ValueError("Delay must be between 0 and 86400 seconds.")
            retry = config.get("retry", {})
            if (
                not isinstance(retry, dict)
                or not 1 <= int(retry.get("max_attempts", 3)) <= 10
                or not 0.1 <= float(retry.get("initial_delay", 2)) <= 120
                or not 1 <= float(retry.get("multiplier", 2)) <= 10
                or not 1 <= float(retry.get("max_delay", 120)) <= 3600
            ):
                raise ValueError("Retry policy is outside the supported limits.")
            connection_id = config.get("connection_id")
            if connection_id and connections is not None:
                connection = connections.get(connection_id)
                if not connection or not connection.enabled:
                    raise ValueError("Select an available credential in this workspace.")
                if kind == "postgres" and connection.type != "postgres":
                    raise ValueError("This node requires a PostgreSQL connection.")
                if (
                    kind == "postgres"
                    and config.get("mode") == "write"
                    and not connection.allow_writes
                ):
                    raise ValueError("This connection does not allow writes.")
                if kind in {"http", "callback"} and connection.type not in {
                    "bearer",
                    "api_key",
                    "basic",
                }:
                    raise ValueError("Select an HTTP authentication connection.")
                if (
                    kind in {"http", "callback"}
                    and "{{" not in config.get("url", "")
                    and urlsplit(config["url"]).hostname
                    not in connection.config.get("allowed_hosts", [])
                ):
                    raise ValueError("This credential is not approved for the request hostname.")
        except Exception as error:
            issue(str(error)[:300], node_id, "config")
        for expression in EXPRESSION.findall(json.dumps(config)):
            if not PATH.fullmatch(expression.strip()):
                issue("Use a supported dot-path expression.", node_id, "config")
            parts = expression.strip().split(".")
            if parts[0] == "nodes" and len(parts) > 1:
                ancestors, stack = set(), list(incoming[node_id])
                while stack:
                    parent = stack.pop()
                    if parent not in ancestors:
                        ancestors.add(parent)
                        stack.extend(incoming[parent])
                aliases = {n.get("alias", n["id"]): n["id"] for n in nodes}
                if aliases.get(parts[1], parts[1]) not in ancestors:
                    issue("Node expressions must reference an upstream node.", node_id, "config")
    aliases = [n.get("alias") for n in nodes if n.get("alias")]
    if len(set(aliases)) != len(aliases) or any(
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", a) for a in aliases
    ):
        issue("Node aliases must be unique names using letters, digits and underscores.")
    return {"valid": not errors, "errors": errors, "warnings": []}
