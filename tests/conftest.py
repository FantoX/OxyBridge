import base64
import os
from urllib.parse import urlsplit

import pytest

test_url = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:oxybridge-test@127.0.0.1:55433/oxybridge_test",
)
if not urlsplit(test_url).path.endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must name a disposable database ending in _test")
os.environ.update(
    DATABASE_URL=test_url,
    APP_ENV="test",
    SECRET_KEY="test-secret-key-with-at-least-thirty-two-characters",
    ENCRYPTION_MASTER_KEY=base64.urlsafe_b64encode(b"x" * 32).decode(),
    CRON_SECRET="test-cron-secret" * 4,
    SETUP_TOKEN="test-setup-token" * 4,
    CORS_ALLOWED_ORIGINS='["http://localhost:5174","http://testserver"]',
    OUTBOUND_PRIVATE_HOSTS='["127.0.0.1","localhost"]',
)

from fastapi.testclient import TestClient

from oxybridge.api import app
from oxybridge.db import Base, transaction, uid
from oxybridge.models import Member, Organization, User, Workspace
from oxybridge.security import passwords


@pytest.fixture(autouse=True)
def clean_database():
    from oxybridge.db import engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def owner():
    with transaction() as db:
        user = User(
            id=uid(),
            email="owner@example.com",
            display_name="Owner",
            password_hash=passwords.hash("OwnerPassword123!"),
        )
        org = Organization(id=uid(), name="Test organization", slug="test")
        db.add_all([user, org])
        db.flush()
        workspace = Workspace(id=uid(), organization_id=org.id, name="Test workspace")
        db.add_all([workspace, Member(organization_id=org.id, user_id=user.id, role="owner")])
        db.flush()
        return {"user_id": user.id, "workspace_id": workspace.id, "organization_id": org.id}


@pytest.fixture
def client(owner):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "OwnerPassword123!"},
        )
        assert response.status_code == 200, response.text
        client.headers.update(
            {"X-CSRF-Token": client.cookies["ob_csrf"], "X-Workspace-ID": owner["workspace_id"]}
        )
        yield client


@pytest.fixture
def fake_http():
    import json
    import threading
    import time
    from collections import Counter
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlsplit

    calls = Counter()
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            query = parse_qs(urlsplit(self.path).query)
            calls[path] += 1
            seen.append(dict(self.headers))
            if path == "/slow":
                time.sleep(0.3)
            if path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", query.get("to", ["/ok"])[0])
                self.end_headers()
                return
            status = (
                int(path.split("/")[-1])
                if path.startswith("/status/")
                else 503
                if path == "/flaky" and calls[path] < 3
                else 200
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = (
                b"x" * 5_300_000
                if path == "/large"
                else b"not-json"
                if path == "/malformed"
                else json.dumps(
                    {
                        "ok": status == 200,
                        "Authorization": self.headers.get("Authorization"),
                        "echo": self.headers.get("Authorization"),
                        "calls": calls[path],
                    }
                ).encode()
            )
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_POST = do_GET

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", calls, seen
    server.shutdown()
    thread.join(timeout=2)


def graph(*kinds):
    nodes = []
    for i, item in enumerate(kinds):
        kind, config = item if isinstance(item, tuple) else (item, {})
        nodes.append(
            {
                "id": uid(),
                "type": kind,
                "label": f"{kind} {i}",
                "alias": f"step_{i}",
                "position": {"x": 100, "y": i * 150},
                "config": config,
            }
        )
    edges = [
        {"id": uid(), "source": a["id"], "target": b["id"], "sourceHandle": "success"}
        for a, b in zip(nodes, nodes[1:])
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def publish(client, definition, name="Test workflow"):
    response = client.post("/api/v1/workflows", json={"name": name, "definition": definition})
    assert response.status_code == 201, response.text
    workflow = response.json()
    response = client.post(f"/api/v1/workflows/{workflow['id']}/publish")
    assert response.status_code == 200, response.text
    return response.json()["workflow"]


def run(client, workflow, payload=None, **kwargs):
    response = client.post(
        f"/api/v1/workflows/{workflow['id']}/run", json={"payload": payload or {}, **kwargs}
    )
    assert response.status_code == 202, response.text
    return client.get("/api/v1/workflow-runs/" + response.json()["run_id"]).json()
