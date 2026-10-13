import socket
from datetime import UTC, datetime

import pytest
from conftest import graph

from oxybridge.engine import retry_delay, transition
from oxybridge.graph import NodeError, condition, next_times, resolve, validate
from oxybridge.security import decrypt, destination, encrypt, redact


def test_expression_preserves_types_and_blocks_internals():
    context = {"trigger": {"body": {"total": 123, "items": ["a"]}}, "env": {"workspace": "test"}}
    assert resolve("{{ trigger.body.total }}", context) == 123
    assert resolve("{{ trigger.body.items.0 }}", context) == "a"
    assert resolve("amount={{ trigger.body.total }}", context) == "amount=123"
    for value in [
        "{{ __class__ }}",
        "{{ trigger.__class__ }}",
        "{{ trigger.body.missing }}",
        "{{ trigger.body.total + 1 }}",
    ]:
        with pytest.raises(NodeError):
            resolve(value, context)


def test_condition_groups_and_missing_exists():
    context = {"trigger": {"body": {"total": 749}}}
    assert condition(
        {
            "mode": "AND",
            "rules": [
                {"left": "{{ trigger.body.total }}", "operator": "greater", "right": 500},
                {"left": "abc", "operator": "contains", "right": "b"},
            ],
        },
        context,
    )
    assert not condition({"left": "{{ trigger.body.missing }}", "operator": "exists"}, context)


def test_graph_rejects_cycles_orphans_duplicate_ids_and_missing_credentials():
    definition = graph("manual", ("transform", {"mapping": {"body": "{{ trigger.body }}"}}))
    assert validate(definition)["valid"]
    definition["edges"].append(
        {
            "id": definition["edges"][0]["id"],
            "source": definition["nodes"][1]["id"],
            "target": definition["nodes"][0]["id"],
            "sourceHandle": "success",
        }
    )
    assert not validate(definition)["valid"]
    definition = graph(
        "manual", ("http", {"url": "https://example.com", "connection_id": "missing"})
    )
    assert not validate(definition, {})["valid"]
    definition["edges"] = []
    assert not validate(definition)["valid"]
    definition["nodes"][1]["id"] = definition["nodes"][0]["id"]
    assert not validate(definition)["valid"]


def test_graph_rejects_raw_secrets_and_external_schema_refs():
    assert not validate(
        graph(
            "manual",
            ("http", {"url": "https://example.com", "headers": {"Authorization": "secret"}}),
        )
    )["valid"]
    assert not validate(
        graph("manual", ("validate", {"schema": {"$ref": "https://evil.invalid/schema"}}))
    )["valid"]


@pytest.mark.parametrize(
    "address", ["127.0.0.2", "10.0.0.1", "169.254.169.254", "::1", "fc00::1", "0.0.0.0"]
)
def test_ssrf_rejects_private_ranges(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))],
    )
    with pytest.raises(ValueError):
        destination("https://example.com/path")


def test_ssrf_rejects_mixed_dns_and_url_credentials(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("8.8.8.8", 80)), (2, 1, 6, "", ("10.0.0.1", 80))],
    )
    with pytest.raises(ValueError):
        destination("https://example.com")
    with pytest.raises(ValueError):
        destination("https://user:password@example.com")
    with pytest.raises(ValueError):
        destination("file:///etc/passwd")


def test_encryption_and_redaction():
    raw = {
        "password": "super-secret",
        "nested": {"Authorization": "Bearer super-secret"},
        "echo": "super-secret",
    }
    encrypted = encrypt(raw)
    assert b"super-secret" not in encrypted
    assert decrypt(encrypted) == raw
    view = redact(raw, ["super-secret"])
    assert "super-secret" not in str(view)
    damaged = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(Exception):
        decrypt(damaged)


def test_retry_is_bounded_and_state_transitions_are_strict():
    assert retry_delay({"jitter": False}, 1) == 2
    assert retry_delay({"jitter": False}, 9) == 120
    from types import SimpleNamespace

    run = SimpleNamespace(status="QUEUED")
    transition(run, "RUNNING")
    with pytest.raises(ValueError):
        transition(run, "QUEUED")


def test_schedule_timezone_and_invalid_cron():
    start = datetime(2026, 10, 12, 1, tzinfo=UTC)
    times = next_times("0 9 * * *", "Asia/Kolkata", start)
    assert len(times) == 5 and times[0].hour == 9
    assert times[0].astimezone(UTC).hour == 3
    for cron, timezone in [("* * * * * *", "UTC"), ("invalid", "UTC"), ("0 9 * * *", "Wrong/Zone")]:
        with pytest.raises(Exception):
            next_times(cron, timezone, start)
