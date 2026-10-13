import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from conftest import graph, publish, run
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from oxybridge.api import app
from oxybridge.config import settings
from oxybridge.db import Session, now, transaction, uid
from oxybridge.engine import create_run, execute, orchestrate
from oxybridge.models import (
    Attempt,
    Connection,
    Member,
    NodeRun,
    Organization,
    Outbox,
    Run,
    Schedule,
    User,
    Workflow,
    Workspace,
)
from oxybridge.security import passwords
from oxybridge.services import dispatch_once, drain, recover_once, schedule_once


def test_manual_transform_immutable_publish_and_revision_conflict(client):
    definition = graph(
        "manual",
        (
            "transform",
            {
                "mapping": {
                    "email": "{{ trigger.body.customer.email }}",
                    "total": "{{ trigger.body.total }}",
                }
            },
        ),
    )
    workflow = publish(client, definition)
    result = run(client, workflow, {"customer": {"email": "a@example.com"}, "total": 749})
    assert result["status"] == "SUCCEEDED", result
    assert result["nodes"][1]["output_data"] == {"email": "a@example.com", "total": 749}
    definition["nodes"][1]["config"]["mapping"] = {"changed": True}
    edit = {"expected_revision": workflow["revision"], "definition": definition}
    assert client.patch(f"/api/v1/workflows/{workflow['id']}", json=edit).status_code == 200
    assert client.patch(f"/api/v1/workflows/{workflow['id']}", json=edit).status_code == 409
    published = client.get(f"/api/v1/workflows/{workflow['id']}/versions").json()[0]
    assert published["definition"]["nodes"][1]["config"]["mapping"] != {"changed": True}
    assert (
        client.get("/api/v1/workflow-runs/" + result["id"]).json()["definition"]
        == published["definition"]
    )


def test_invalid_workflow_cannot_publish(client):
    response = client.post(
        "/api/v1/workflows", json={"name": "Invalid", "definition": graph("http")}
    )
    checked = client.post("/api/v1/workflows/" + response.json()["id"] + "/publish")
    assert checked.status_code == 422
    assert checked.json()["detail"]["code"] == "WORKFLOW_INVALID"


@pytest.mark.parametrize("total,selected", [(749, "high"), (100, "standard")])
def test_branching_merge_skips_unselected_path(client, total, selected):
    from oxybridge.templates import routing_template

    definition = routing_template()
    workflow = publish(client, definition)
    result = run(
        client,
        workflow,
        {"order_id": "ORD-1", "total": total, "customer": {"email": "a@example.com"}},
    )
    assert result["status"] == "SUCCEEDED", result
    nodes = {n["label"]: n for n in result["nodes"]}
    assert nodes["Priority fulfillment"]["status"] == (
        "SUCCEEDED" if selected == "high" else "SKIPPED"
    )
    assert nodes["Standard fulfillment"]["status"] == (
        "SUCCEEDED" if selected == "standard" else "SKIPPED"
    )
    assert nodes["Prepare reservation"]["status"] == "SUCCEEDED"


def test_invalid_payload_is_inspectable_dead_letter(client):
    workflow = publish(
        client,
        graph("manual", ("validate", {"schema": {"type": "object", "required": ["order_id"]}})),
    )
    result = run(client, workflow)
    assert result["status"] == "FAILED", result
    assert result["error_code"] == "PAYLOAD_INVALID"
    assert client.get("/api/v1/dead-letters").json()[0]["run_id"] == result["id"]


def test_http_transient_retry_recovers_and_records_attempts(client, fake_http):
    base, calls, seen = fake_http
    workflow = publish(
        client,
        graph(
            "manual",
            (
                "http",
                {
                    "url": base + "/flaky",
                    "timeout": 2,
                    "retry": {"initial_delay": 0.1, "max_attempts": 3, "jitter": False},
                },
            ),
        ),
    )
    result = run(client, workflow)
    for _ in range(10):
        if result["status"] in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(0.22)
        result = client.post("/api/v1/workflow-runs/" + result["id"] + "/advance").json()
    assert result["status"] == "SUCCEEDED", result
    http_node = result["nodes"][1]
    assert http_node["attempt"] == 3 and len(http_node["attempts"]) == 3
    assert calls["/flaky"] == 3
    assert len({request["Idempotency-Key"] for request in seen}) == 1
    assert [a["http_status"] for a in http_node["attempts"][:2]] == [503, 503]


def test_http_400_is_not_retried_and_recovery_preserves_history(client, fake_http):
    base, calls, _ = fake_http
    workflow = publish(
        client, graph("manual", ("http", {"url": base + "/status/400", "timeout": 2}))
    )
    original = run(client, workflow)
    assert original["status"] == "FAILED", original
    assert calls["/status/400"] == 1
    response = client.post("/api/v1/workflow-runs/" + original["id"] + "/rerun")
    assert response.status_code == 202
    next_run = client.get("/api/v1/workflow-runs/" + response.json()["run_id"]).json()
    assert next_run["id"] != original["id"] and next_run["recovery_of"] == original["id"]
    assert next_run["version_id"] == original["version_id"]
    assert client.get("/api/v1/workflow-runs/" + original["id"]).json()["status"] == "FAILED"


def test_http_credentials_are_encrypted_and_redacted(client, fake_http):
    base, _, _ = fake_http
    connection = client.post(
        "/api/v1/connections",
        json={
            "name": "API",
            "type": "bearer",
            "secret": {"token": "secret-token-123"},
            "allowed_hosts": ["127.0.0.1"],
        },
    ).json()
    assert "secret-token-123" not in str(connection)
    with Session() as db:
        stored = db.get(Connection, connection["id"])
        assert b"secret-token-123" not in stored.encrypted_secret
    workflow = publish(
        client, graph("manual", ("http", {"url": base + "/ok", "connection_id": connection["id"]}))
    )
    result = run(client, workflow)
    assert result["status"] == "SUCCEEDED", result
    assert "secret-token-123" not in str(result)
    assert result["nodes"][1]["output_data"]["body"]["Authorization"] == "[redacted]"
    assert "[redacted]" in result["nodes"][1]["output_data"]["body"]["echo"]


def test_idempotency_duplicate_and_conflicting_input(client):
    workflow = publish(client, graph("manual"))
    first = run(client, workflow, {"amount": 1}, idempotency_key="order-1")
    second = run(client, workflow, {"amount": 1}, idempotency_key="order-1")
    assert first["id"] == second["id"]
    response = client.post(
        "/api/v1/workflows/" + workflow["id"] + "/run",
        json={"payload": {"amount": 2}, "idempotency_key": "order-1"},
    )
    assert response.status_code == 409


def test_duplicate_node_delivery_only_executes_once(client, fake_http):
    base, calls, _ = fake_http
    workflow = publish(client, graph("manual", ("http", {"url": base + "/ok"})))
    with transaction() as db:
        fresh = create_run(db, db.get(Workflow, workflow["id"]), {})
        run_id = fresh.id
    orchestrate(run_id)
    with Session() as db:
        trigger_id = db.scalar(
            select(NodeRun.id).where(NodeRun.run_id == run_id, NodeRun.status == "QUEUED")
        )
    execute(trigger_id)
    orchestrate(run_id)
    with Session() as db:
        node_id = db.scalar(
            select(NodeRun.id).where(NodeRun.run_id == run_id, NodeRun.status == "QUEUED")
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: execute(node_id), range(4)))
    assert calls["/ok"] == 1


def test_parallel_drains_preserve_all_run_outputs(client):
    workflow = publish(
        client, graph("manual", ("transform", {"mapping": {"value": "{{ trigger.body.value }}"}}))
    )
    with transaction() as db:
        ids = [create_run(db, db.get(Workflow, workflow["id"]), {"value": i}).id for i in range(20)]
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(drain, ids))
    with Session() as db:
        assert all(db.get(Run, run_id).status == "SUCCEEDED" for run_id in ids)
        for i, run_id in enumerate(ids):
            mapped = db.scalar(
                select(NodeRun).where(NodeRun.run_id == run_id, NodeRun.node_type == "transform")
            )
            assert mapped.output_data == {"value": i}
    print(f"20 runs, 5 concurrent drains: {time.monotonic() - started:.2f}s, zero lost outputs")


def test_expired_run_does_not_start_an_external_action(client, fake_http):
    base, calls, _ = fake_http
    workflow = publish(client, graph("manual", ("http", {"url": base + "/ok"})))
    with transaction() as db:
        fresh = create_run(db, db.get(Workflow, workflow["id"]), {})
        run_id = fresh.id
    orchestrate(run_id)
    with Session() as db:
        trigger_id = db.scalar(
            select(NodeRun.id).where(NodeRun.run_id == run_id, NodeRun.status == "QUEUED")
        )
    execute(trigger_id)
    orchestrate(run_id)
    with transaction() as db:
        db.get(Run, run_id).created_at = now() - timedelta(seconds=settings().run_max_seconds + 1)
        node_id = db.scalar(
            select(NodeRun.id).where(NodeRun.run_id == run_id, NodeRun.status == "QUEUED")
        )
    execute(node_id)
    drain(run_id)
    assert calls["/ok"] == 0
    with Session() as db:
        assert db.get(Run, run_id).status == "TIMED_OUT"


def test_cancel_queued_run_and_bounded_delay(client, owner):
    workflow = publish(
        client,
        graph("manual", ("delay", {"seconds": 60}), ("transform", {"mapping": {"done": True}})),
    )
    result = run(client, workflow)
    assert result["status"] == "RUNNING" and result["nodes"][1]["status"] == "RETRY_WAIT"
    response = client.post("/api/v1/workflow-runs/" + result["id"] + "/cancel")
    assert response.status_code == 200
    current = client.get("/api/v1/workflow-runs/" + result["id"]).json()
    assert current["status"] == "CANCELLED"
    assert current["nodes"][2]["status"] == "CANCELLED"


def test_expired_worker_lease_is_recoverable(client):
    workflow = publish(client, graph("manual"))
    with transaction() as db:
        run = create_run(db, db.get(Workflow, workflow["id"]), {})
        run_id = run.id
    orchestrate(run_id)
    with transaction() as db:
        node = db.scalar(select(NodeRun).where(NodeRun.run_id == run_id))
        node.status, node.attempt, node.lease_until = "RUNNING", 1, now() - timedelta(seconds=1)
        db.add(Attempt(node_run_id=node.id, number=1, status="RUNNING"))
    recover_once()
    drain(run_id)
    with Session() as db:
        assert db.get(Run, run_id).status == "SUCCEEDED"
        assert db.scalar(select(func.count()).select_from(Attempt)) == 2


def test_outbox_failure_keeps_durable_event(client, monkeypatch):
    workflow = publish(client, graph("manual"))
    with transaction() as db:
        created = create_run(db, db.get(Workflow, workflow["id"]), {})
        run_id = created.id
    import oxybridge.services as services

    original = services.orchestrate
    monkeypatch.setattr(
        services, "orchestrate", lambda *_: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    assert dispatch_once(run_id)
    with Session() as db:
        event = db.scalar(select(Outbox).where(Outbox.published_at.is_(None)))
        assert event.last_error and not event.claim_token
    monkeypatch.setattr(services, "orchestrate", original)
    with transaction() as db:
        event = db.scalar(select(Outbox).where(Outbox.published_at.is_(None)))
        event.available_at = now()
    drain(run_id)
    with Session() as db:
        assert db.get(Run, run_id).status == "SUCCEEDED"


def test_schedule_concurrent_ticks_create_one_run(client):
    workflow = publish(client, graph("manual"))
    response = client.post(
        "/api/v1/schedules",
        json={"workflow_id": workflow["id"], "cron": "0 9 * * *", "timezone": "Asia/Kolkata"},
    )
    assert response.status_code == 201, response.text
    schedule_id = response.json()["id"]
    with transaction() as db:
        db.get(Schedule, schedule_id).next_run_at = now() - timedelta(minutes=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: schedule_once(), range(2)))
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Run)) == 1


def test_cookie_csrf_rotation_and_logout(client):
    assert (
        client.post(
            "/api/v1/workflows", json={"name": "CSRF"}, headers={"X-CSRF-Token": ""}
        ).status_code
        == 403
    )
    old_session = client.cookies["ob_session"]
    assert client.post("/api/v1/auth/refresh").status_code == 200
    assert client.cookies["ob_session"] != old_session
    client.headers["X-CSRF-Token"] = client.cookies["ob_csrf"]
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/workflows").status_code == 401


def test_rbac_and_cross_organization_isolation(client, owner):
    workflow = publish(client, graph("manual"))
    with transaction() as db:
        outsider = User(
            id=uid(),
            email="viewer@example.com",
            display_name="Viewer",
            password_hash=passwords.hash("ViewerPassword123!"),
        )
        org = Organization(id=uid(), name="Other tenant", slug="other")
        db.add_all([outsider, org])
        db.flush()
        workspace = Workspace(id=uid(), organization_id=org.id, name="Other workspace")
        db.add_all([workspace, Member(organization_id=org.id, user_id=outsider.id, role="viewer")])
        db.flush()
        other_id = workspace.id
    with TestClient(app) as viewer:
        assert (
            viewer.post(
                "/api/v1/auth/login",
                json={"email": "viewer@example.com", "password": "ViewerPassword123!"},
            ).status_code
            == 200
        )
        viewer.headers.update(
            {"X-CSRF-Token": viewer.cookies["ob_csrf"], "X-Workspace-ID": other_id}
        )
        assert viewer.get("/api/v1/workflows/" + workflow["id"]).status_code == 404
        assert viewer.post("/api/v1/workflows", json={"name": "Denied"}).status_code == 403
        assert (
            viewer.get(
                "/api/v1/connections", headers={"X-Workspace-ID": owner["workspace_id"]}
            ).status_code
            == 403
        )


def test_api_key_scopes_and_revocation(client):
    workflow = publish(client, graph("manual"))
    key = client.post("/api/v1/api-keys", json={"name": "Runner", "scopes": ["runs:write"]}).json()
    headers = {"Authorization": "Bearer " + key["token"]}
    assert client.get("/api/v1/workflows", headers=headers).status_code == 403
    response = client.post(
        "/api/v1/workflows/" + workflow["id"] + "/run", json={"payload": {}}, headers=headers
    )
    assert response.status_code == 202, response.text
    snapshot = client.post(
        "/api/v1/workflows/" + workflow["id"] + "/run", json={"test": True}
    ).json()
    assert (
        client.post(
            "/api/v1/workflow-runs/" + snapshot["run_id"] + "/rerun", headers=headers
        ).status_code
        == 403
    )
    assert client.delete("/api/v1/api-keys/" + key["id"]).status_code == 200
    assert (
        client.post(
            "/api/v1/workflows/" + workflow["id"] + "/run", json={}, headers=headers
        ).status_code
        == 401
    )


def test_webhook_token_signature_replay_and_body_limits(client):
    import hashlib
    import hmac
    import json

    workflow = publish(client, graph("webhook"))
    secret = "webhook-signing-secret-123"
    hook = client.post(
        "/api/v1/workflows/" + workflow["id"] + "/webhook", json={"hmac_secret": secret}
    ).json()
    from urllib.parse import urlsplit

    path = urlsplit(hook["url"]).path
    assert client.post(path, json={}).status_code == 401
    timestamp, body = str(int(time.time())), json.dumps({"order": 1}).encode()
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-OxyBridge-Timestamp": timestamp,
        "X-OxyBridge-Signature": signature,
    }
    first = client.post(path, content=body, headers=headers)
    second = client.post(path, content=body, headers=headers)
    assert first.status_code == 202, first.text
    assert first.json()["run_id"] == second.json()["run_id"]
    assert client.post(path, content=b"x" * 1_048_577, headers=headers).status_code == 413
    assert (
        client.post(
            path, content=body, headers={**headers, "X-OxyBridge-Timestamp": "1"}
        ).status_code
        == 401
    )


def test_cron_requires_secret_and_health_is_process_only(client):
    assert client.get("/api/v1/system/tick").status_code == 401
    assert (
        client.get(
            "/api/v1/system/tick", headers={"Authorization": "Bearer " + settings().cron_secret}
        ).status_code
        == 200
    )
    assert client.get("/health/live").json()["status"] == "alive"


def test_execution_stream_releases_connections_and_reads_off_event_loop(client, owner, monkeypatch):
    import asyncio
    import importlib
    import json
    import threading
    from types import SimpleNamespace

    api_module = importlib.import_module("oxybridge.api")
    result = run(client, publish(client, graph("manual")))
    original_view = api_module.run_view
    event_loop_thread = threading.get_ident()

    def checked_view(*args):
        assert threading.get_ident() != event_loop_thread
        return original_view(*args)

    monkeypatch.setattr(api_module, "run_view", checked_view)
    with Session() as db:
        response = api_module.events(
            result["id"],
            p=SimpleNamespace(workspace=SimpleNamespace(id=owner["workspace_id"])),
            db=db,
        )
        assert api_module.engine.pool.checkedout() == 0

        async def consume():
            snapshot = await anext(response.body_iterator)
            assert api_module.engine.pool.checkedout() == 0
            assert json.loads(snapshot.split("data: ", 1)[1])["id"] == result["id"]
            with pytest.raises(StopAsyncIteration):
                await anext(response.body_iterator)

        asyncio.run(consume())
