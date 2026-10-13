"""Check an isolated deployment's continuous processing without external action nodes."""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    email, password = os.environ.get("E2E_EMAIL"), os.environ.get("E2E_PASSWORD")
    if not email or not password:
        parser.error("Set E2E_EMAIL and E2E_PASSWORD for an isolated test account.")
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=45) as client:

        def request(method, path, expected=200, **values):
            response = client.request(method, path, **values)
            assert response.status_code == expected, (
                f"Unexpected {response.status_code} at a runtime check"
            )
            return response.json()

        page = client.get("/")
        assert page.status_code == 200 and 'id="root"' in page.text
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        for path in ("/.env", "/api/v1/missing", "/assets/missing.js"):
            assert client.get(path).status_code == 404
        assert request("GET", "/health/ready")["database"] == "healthy"
        request("GET", "/api/v1/system/tick", expected=401)
        request("POST", "/api/v1/auth/login", json={"email": email, "password": password})
        client.headers["X-CSRF-Token"] = client.cookies["ob_csrf"]
        me = request("GET", "/api/v1/auth/me")
        client.headers["X-Workspace-ID"] = me["workspaces"][0]["id"]
        nodes = [
            {
                "id": str(uuid4()),
                "type": kind,
                "label": label,
                "alias": f"step_{i}",
                "position": {"x": 100, "y": i * 160},
                "config": config,
            }
            for i, (kind, label, config) in enumerate(
                [
                    ("webhook", "Incoming event", {}),
                    ("delay", "Durable wait", {"seconds": 12}),
                    (
                        "set",
                        "Verified outcome",
                        {"mapping": {"verified": True, "run_id": "{{ run.id }}"}},
                    ),
                ]
            )
        ]
        definition = {
            "schema_version": 1,
            "nodes": nodes,
            "edges": [
                {
                    "id": str(uuid4()),
                    "source": a["id"],
                    "target": b["id"],
                    "sourceHandle": "success",
                }
                for a, b in zip(nodes, nodes[1:])
            ],
        }
        workflow = request(
            "POST",
            "/api/v1/workflows",
            expected=201,
            json={
                "name": "Runtime verification " + time.strftime("%Y%m%d-%H%M%S"),
                "description": "Controlled continuous-service check; no external action nodes.",
                "definition": definition,
            },
        )
        prefix, schedule = "/api/v1/workflows/" + workflow["id"], None
        try:
            request("POST", prefix + "/publish")
            secret = secrets.token_urlsafe(32)
            hook = request("POST", prefix + "/webhook", json={"hmac_secret": secret})
            hook_path = "/hooks/" + hook["url"].split("/hooks/", 1)[1]
            body, stamp = (
                json.dumps({"event": "runtime-verification"}).encode(),
                str(int(time.time())),
            )
            signature = hmac.new(
                secret.encode(), stamp.encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            headers = {
                "Content-Type": "application/json",
                "X-OxyBridge-Timestamp": stamp,
                "X-OxyBridge-Signature": signature,
            }
            accepted = request("POST", hook_path, expected=202, content=body, headers=headers)
            duplicate = request("POST", hook_path, expected=202, content=body, headers=headers)
            assert duplicate["run_id"] == accepted["run_id"]
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                run = request("GET", "/api/v1/workflow-runs/" + accepted["run_id"])
                if run["status"] == "SUCCEEDED":
                    break
                assert run["status"] not in {"FAILED", "TIMED_OUT", "CANCELLED"}
                time.sleep(1)
            assert run["status"] == "SUCCEEDED", "Continuous dispatcher did not resume the delay"
            assert run["nodes"][-1]["output_data"]["run_id"] == run["id"]
            print("Signed webhook, replay protection, and unattended durable delay passed.")
            schedule = request(
                "POST",
                "/api/v1/schedules",
                expected=201,
                json={
                    "workflow_id": workflow["id"],
                    "cron": "* * * * *",
                    "timezone": "UTC",
                },
            )
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                runs = request("GET", "/api/v1/workflow-runs?workflow_id=" + workflow["id"])
                scheduled = next((run for run in runs if run["trigger_type"] == "schedule"), None)
                if scheduled and scheduled["status"] == "SUCCEEDED":
                    break
                time.sleep(1)
            assert scheduled and scheduled["status"] == "SUCCEEDED", (
                "Continuous scheduler did not complete a due run"
            )
            print(
                "Continuous cron scheduling passed without browser advancement or a scheduler tick."
            )
        finally:
            if schedule:
                request("DELETE", "/api/v1/schedules/" + schedule["id"])
            request("DELETE", prefix)
            request("POST", "/api/v1/auth/logout")


if __name__ == "__main__":
    main()
