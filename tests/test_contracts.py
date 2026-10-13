import socket
from datetime import timedelta

import pytest
from conftest import graph, publish, run
from sqlalchemy import select, text

from oxybridge.config import settings
from oxybridge.db import Session, engine, now, transaction
from oxybridge.graph import NodeError
from oxybridge.models import DeadLetter, Run
from oxybridge.nodes import http_request, postgres_query
from oxybridge.services import retention_once


@pytest.mark.parametrize("code", [200, 201])
def test_http_accepts_expected_success(fake_http, code):
    base, _, _ = fake_http
    response = http_request(
        {"url": base + "/status/" + str(code)}, {"run": {"id": "run", "node_id": "node"}}
    )
    assert response["status"] == code


@pytest.mark.parametrize(
    "code,retryable",
    [(400, False), (401, False), (404, False), (429, True), (500, True), (503, True)],
)
def test_http_status_contract(fake_http, code, retryable):
    base, _, _ = fake_http
    with pytest.raises(NodeError) as caught:
        http_request(
            {"url": base + "/status/" + str(code)}, {"run": {"id": "run", "node_id": "node"}}
        )
    assert caught.value.http_status == code and caught.value.retryable == retryable


def test_timeout_malformed_json_and_large_response(fake_http):
    base, _, _ = fake_http
    context = {"run": {"id": "run", "node_id": "node"}}
    with pytest.raises(NodeError) as caught:
        http_request({"url": base + "/slow", "timeout": 0.05}, context)
    assert caught.value.code == "HTTP_TIMEOUT"
    assert http_request({"url": base + "/malformed"}, context)["body"] == "not-json"
    with pytest.raises(NodeError) as caught:
        http_request({"url": base + "/large"}, context)
    assert caught.value.code == "HTTP_RESPONSE_TOO_LARGE"


def test_redirects_recheck_dns_and_do_not_forward_credentials(fake_http, monkeypatch):
    base, _, seen = fake_http
    context = {"run": {"id": "run", "node_id": "node"}}
    redirected = http_request({"url": base + "/redirect", "follow_redirects": True}, context)
    assert redirected["status"] == 200
    other_host = base.replace("127.0.0.1", "localhost")
    http_request(
        {"url": base + "/redirect?to=" + other_host + "/ok", "follow_redirects": True},
        context,
        {"token": "private-secret"},
        "bearer",
        ["127.0.0.1"],
    )
    assert seen[-1].get("Authorization") is None
    with pytest.raises(NodeError) as caught:
        http_request(
            {"url": base + "/redirect?to=http://10.0.0.1/", "follow_redirects": True}, context
        )
    assert caught.value.code == "SSRF_BLOCKED"


def test_request_transport_pins_resolved_dns(fake_http, monkeypatch):
    base, _, _ = fake_http
    port = int(base.rsplit(":", 1)[1])
    real = socket.getaddrinfo
    count = 0

    def resolver(host, target_port, *args, **kwargs):
        nonlocal count
        if host == "approved.test":
            count += 1
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("127.0.0.1" if count == 1 else "10.0.0.1", port),
                )
            ]
        return real(host, target_port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    policy = settings()
    monkeypatch.setattr(
        policy, "outbound_private_hosts", [*policy.outbound_private_hosts, "approved.test"]
    )
    response = http_request(
        {"url": f"http://approved.test:{port}/ok"}, {"run": {"id": "run", "node_id": "node"}}
    )
    assert response["status"] == 200 and count == 1


def test_postgres_parameters_read_only_and_row_limits():
    credential = {
        "host": "127.0.0.1",
        "port": 55433,
        "database": "oxybridge_test",
        "username": "postgres",
        "password": "oxybridge-test",
        "sslmode": "disable",
    }
    result = postgres_query(
        {
            "query": "SELECT %(value)s::text AS value",
            "parameters": {"value": "'; DROP TABLE users; --"},
        },
        {},
        credential,
    )
    assert result["rows"][0]["value"] == "'; DROP TABLE users; --"
    with pytest.raises(NodeError):
        postgres_query(
            {"query": "CREATE TABLE malicious_test (id int)", "mode": "read"}, {}, credential
        )
    with pytest.raises(NodeError) as caught:
        postgres_query({"query": "SELECT generate_series(1, 1001) AS n"}, {}, credential)
    assert caught.value.code == "DATABASE_RESULT_TOO_LARGE"
    with pytest.raises(NodeError) as caught:
        postgres_query({"query": "SELECT 1", "mode": "write"}, {}, credential)
    assert caught.value.code == "FORBIDDEN"


@pytest.mark.parametrize(
    "kind,secret",
    [
        ("bearer", {"token": "credential-123456"}),
        ("basic", {"username": "demo-user", "password": "abc"}),
    ],
)
def test_secret_redaction_survives_downstream_mapping(client, fake_http, kind, secret):
    base, _, _ = fake_http
    connection = client.post(
        "/api/v1/connections",
        json={
            "name": "Token",
            "type": kind,
            "secret": secret,
            "allowed_hosts": ["127.0.0.1"],
        },
    ).json()
    workflow = publish(
        client,
        graph(
            "manual",
            ("http", {"url": base + "/ok", "connection_id": connection["id"]}),
            ("transform", {"mapping": {"copied": "{{ nodes.step_1.output.body.echo }}"}}),
        ),
    )
    result = run(client, workflow)
    assert result["status"] == "SUCCEEDED"
    assert "credential-123456" not in str(result)
    if kind == "basic":
        import base64

        assert base64.b64encode(b"demo-user:abc").decode() not in str(result)


def test_unsafe_draft_headers_are_rejected_before_storage(client):
    response = client.post(
        "/api/v1/workflows",
        json={
            "name": "Secrets",
            "definition": graph(
                "manual",
                (
                    "http",
                    {
                        "url": "https://example.com",
                        "headers": {"Authorization": "Bearer raw-credential"},
                    },
                ),
            ),
        },
    )
    assert response.status_code == 422

    assert "raw-credential" not in response.text
    assert not any(w["name"] == "Secrets" for w in client.get("/api/v1/workflows").json())


@pytest.mark.parametrize(
    "config",
    [
        {"url": "https://example.com?api_key=private-value"},
        {"url": "https://example.com?api_key=private-value&api_key={{ trigger.body.api_key }}"},
        {"url": "https://example.com", "query": {"token": "private-value"}},
        {"url": "https://example.com", "body": {"nested": {"password": "private-value"}}},
    ],
)
def test_inline_authentication_is_rejected_before_draft_storage(client, config):
    definition = graph("manual", ("http", config))
    from oxybridge.graph import validate

    assert not validate(definition)["valid"]
    response = client.post(
        "/api/v1/workflows", json={"name": "Inline credentials", "definition": definition}
    )
    assert response.status_code == 422
    assert "private-value" not in response.text


def test_runtime_authentication_expressions_can_be_saved_without_inline_secrets(client):
    definition = graph(
        "manual",
        (
            "http",
            {
                "url": "https://example.com?api_key={{ trigger.body.api_key }}",
                "body": {"password": "{{ trigger.body.password }}"},
            },
        ),
    )
    assert (
        client.post(
            "/api/v1/workflows", json={"name": "Runtime values", "definition": definition}
        ).status_code
        == 201
    )


def test_retention_detaches_resolved_recovery_links(client):
    original = run(
        client,
        publish(client, graph("manual", ("validate", {"schema": {"required": ["missing"]}}))),
    )
    recovered = run(client, publish(client, graph("manual")))
    with transaction() as db:
        dead = db.scalar(select(DeadLetter).where(DeadLetter.run_id == original["id"]))
        dead.recovery_run_id, dead.resolved_at = recovered["id"], now()
        db.get(Run, recovered["id"]).created_at = now() - timedelta(days=100)
    retention_once()
    with Session() as db:
        assert db.get(Run, recovered["id"]) is None
        assert (
            db.scalar(select(DeadLetter).where(DeadLetter.run_id == original["id"])).recovery_run_id
            is None
        )


def test_exhausted_retries_are_dead_lettered(client, fake_http):
    base, calls, _ = fake_http
    workflow = publish(
        client,
        graph(
            "manual",
            (
                "http",
                {
                    "url": base + "/status/503",
                    "retry": {"max_attempts": 3, "initial_delay": 0.1, "jitter": False},
                },
            ),
        ),
    )
    result = run(client, workflow)
    assert result["status"] == "FAILED" and calls["/status/503"] == 3
    assert result["retries"] == 2
    assert client.get("/api/v1/dead-letters").json()[0]["attempts"] == 3


def test_retention_preserves_unresolved_failures_and_removes_success_payloads(client):
    successful = run(client, publish(client, graph("manual")), {"value": "old"})
    failed = run(
        client,
        publish(client, graph("manual", ("validate", {"schema": {"required": ["missing"]}}))),
    )
    with transaction() as db:
        db.get(Run, successful["id"]).created_at = now() - timedelta(days=40)
        db.get(Run, failed["id"]).created_at = now() - timedelta(days=100)
    retention_once()
    with Session() as db:
        assert db.get(Run, successful["id"]).encrypted_payload is None
        assert db.get(Run, failed["id"]) is not None
        assert (
            db.scalar(select(DeadLetter).where(DeadLetter.run_id == failed["id"])).resolved_at
            is None
        )


def test_migrations_from_empty_database_and_upgrade_idempotent():
    from alembic import command
    from alembic.config import Config

    from oxybridge.db import Base

    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        assert (
            connection.scalar(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            )
            >= 19
        )
