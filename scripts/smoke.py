"""Verify a deployed instance using an archived verification copy of its fulfillment demo."""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    credentials = (
        {"email": os.environ["E2E_EMAIL"], "password": os.environ["E2E_PASSWORD"]}
        if os.environ.get("E2E_EMAIL") and os.environ.get("E2E_PASSWORD")
        else json.loads(Path(".local/login.json").read_text())
    )
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=90) as client:
        if args.url.startswith("https://"):
            page = client.get("/")
            assert page.status_code == 200
            assert page.headers.get("x-frame-options") == "DENY"
            assert page.headers.get("x-content-type-options") == "nosniff"

        def request(method, path, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.status_code == expected, (
                f"{method} {path.split('/hooks/')[0]}: unexpected status {response.status_code}"
            )
            return response.json()

        assert request("GET", "/health/ready")["database"] == "healthy"
        request(
            "POST", "/api/v1/auth/login", json={k: credentials[k] for k in ("email", "password")}
        )
        client.headers["X-CSRF-Token"] = client.cookies["ob_csrf"]
        me = request("GET", "/api/v1/auth/me")
        client.headers["X-Workspace-ID"] = me["workspaces"][0]["id"]
        workflows = request("GET", "/api/v1/workflows")
        demo = next(w for w in workflows if w["name"] == "Order Fulfillment Demo")
        demo = request("GET", "/api/v1/workflows/" + demo["id"])
        assert all(
            n["config"].get("url", "").startswith("https://postman-echo.com/")
            for n in demo["definition"]["nodes"]
            if n["type"] in {"http", "callback"}
        ), "Verification requires the unchanged echo demo, not business endpoints"
        workflow = request(
            "POST",
            "/api/v1/workflows",
            expected=201,
            json={
                "name": "Release verification " + time.strftime("%Y%m%d-%H%M%S"),
                "description": "Controlled hosted validation, archived after completion.",
                "definition": demo["definition"],
            },
        )
        prefix = "/api/v1/workflows/" + workflow["id"]
        try:
            request("POST", prefix + "/publish")
            secret = secrets.token_urlsafe(32)
            hook = request("POST", prefix + "/webhook", json={"hmac_secret": secret})
            # APP_BASE_URL can be the production alias when checking a preview deployment.
            path = "/hooks/" + hook["url"].split("/hooks/", 1)[1]
            request("POST", path, expected=401, json={})
            run_ids = []
            for total in (749, 49):
                body = json.dumps(
                    {
                        "order_id": "VERIFY-" + secrets.token_hex(5),
                        "total": total,
                        "customer": {"email": "verification@example.com"},
                    }
                ).encode()
                timestamp = str(int(time.time()))
                signature = hmac.new(
                    secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
                ).hexdigest()
                headers = {
                    "Content-Type": "application/json",
                    "X-OxyBridge-Timestamp": timestamp,
                    "X-OxyBridge-Signature": signature,
                }
                result = request("POST", path, expected=202, content=body, headers=headers)
                duplicate = request("POST", path, expected=202, content=body, headers=headers)
                assert duplicate["run_id"] == result["run_id"], (
                    "Signed replay created a duplicate run"
                )
                run_id = result["run_id"]
                run_ids.append(run_id)
                for _ in range(30):
                    run = request("GET", "/api/v1/workflow-runs/" + run_id)
                    if run["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"}:
                        break
                    request("POST", "/api/v1/workflow-runs/" + run_id + "/advance")
                    time.sleep(1)
                assert run["status"] == "SUCCEEDED", "Fulfillment execution did not succeed"
                stored = next(n for n in run["nodes"] if n["node_type"] == "postgres")[
                    "output_data"
                ]["rows"][0]
                assert stored["order_id"] == json.loads(body)["order_id"]
                assert stored["priority"] == ("high" if total > 500 else "standard")
                assert "postgresql://" not in json.dumps(run)
                print(
                    f"Hosted fulfillment passed: total={total}, signed replay deduplicated, PostgreSQL write verified."
                )
            failed = request(
                "POST",
                prefix + "/run",
                expected=202,
                json={"payload": {"order_id": "INVALID-VERIFY"}},
            )
            for _ in range(20):
                failure = request("GET", "/api/v1/workflow-runs/" + failed["run_id"])
                if failure["status"] == "FAILED":
                    break
                request("POST", "/api/v1/workflow-runs/" + failed["run_id"] + "/advance")
                time.sleep(1)
            assert failure["status"] == "FAILED"
            dead = next(
                d for d in request("GET", "/api/v1/dead-letters") if d["run_id"] == failed["run_id"]
            )
            request("POST", "/api/v1/dead-letters/" + dead["id"] + "/resolve")
            print("Hosted invalid input rejected; failure and dead letter remain inspectable.")
            print("Verified run IDs: " + ", ".join(run_ids))
        finally:
            request("DELETE", prefix)
            request("POST", "/api/v1/auth/logout")


if __name__ == "__main__":
    main()

