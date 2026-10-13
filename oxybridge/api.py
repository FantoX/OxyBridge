import json
import secrets
import smtplib
import ssl
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from uuid import UUID

from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter as MetricCounter
from prometheus_client import Histogram, generate_latest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from oxybridge import schemas as S
from oxybridge.auth import (
    Principal,
    audit,
    cookie_session,
    fail,
    make_session,
    origin_check,
    principal,
    require,
)
from oxybridge.config import settings
from oxybridge.db import Session as DBSession
from oxybridge.db import engine, get_db, now, uid
from oxybridge.engine import create_run, enqueue, transition
from oxybridge.graph import TERMINAL, NodeError, next_times, validate
from oxybridge.models import (
    ApiKey,
    Attempt,
    Audit,
    AuthSession,
    Connection,
    DeadLetter,
    Heartbeat,
    Member,
    NodeRun,
    Organization,
    Outbox,
    PasswordReset,
    Run,
    Schedule,
    User,
    Version,
    Workflow,
    Workspace,
)
from oxybridge.security import content_hash, decrypt, digest, encrypt, limiter, passwords, redact
from oxybridge.services import drain, recover_once, retention_once, schedule_once
from oxybridge.telemetry import configure, log, tracer

REQUESTS = MetricCounter("oxybridge_api_requests_total", "API responses", ["method", "status"])
LATENCY = Histogram("oxybridge_api_request_seconds", "API latency")


@asynccontextmanager
async def lifespan(app):
    configure("api")
    yield
    engine.dispose()


app = FastAPI(title="OxyBridge", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=[
        "Content-Type",
        "X-CSRF-Token",
        "X-Workspace-ID",
        "Authorization",
        "Idempotency-Key",
        "X-Setup-Token",
    ],
)


def protect(response, request_id, path):
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
    )
    if path.startswith(("/api", "/hooks")):
        response.headers["Cache-Control"] = "no-store"
    if path != "/docs" and path != "/redoc":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
    if settings().session_cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.middleware("http")
async def boundary(request, call_next):
    request_id, started = uid(), time.monotonic()
    if request.method in {"POST", "PATCH", "PUT"}:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > settings().webhook_max_body_bytes:
                return protect(
                    JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "The request body exceeds the configured size limit.",
                            }
                        },
                    ),
                    request_id,
                    request.url.path,
                )
        request._body = bytes(raw)
        if raw and "application/json" in request.headers.get("content-type", "").lower():
            try:
                json.loads(
                    raw,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON number")
                    ),
                )
            except (ValueError, UnicodeDecodeError, RecursionError):
                return protect(
                    JSONResponse(
                        status_code=400,
                        content={
                            "detail": {
                                "code": "PAYLOAD_INVALID",
                                "message": "Send valid JSON with finite numbers and bounded nesting.",
                            }
                        },
                    ),
                    request_id,
                    request.url.path,
                )
    with tracer.start_as_current_span("http." + request.method):
        try:
            response = await call_next(request)
        except Exception:
            log("api.request_failed", request_id=request_id)
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": {
                        "code": "INTERNAL_ERROR",
                        "message": "The request could not complete. Use the request ID to investigate.",
                    }
                },
            )
    protect(response, request_id, request.url.path)
    REQUESTS.labels(request.method, response.status_code).inc()
    LATENCY.observe(time.monotonic() - started)
    return response


@app.exception_handler(NodeError)
async def node_error(request, error):
    status = 409 if error.code in {"IDEMPOTENCY_CONFLICT", "WORKFLOW_DISABLED"} else 422
    return JSONResponse(
        status_code=status, content={"detail": {"code": error.code, "message": str(error)}}
    )


@app.exception_handler(RequestValidationError)
async def input_error(request, error):
    fields = [
        {
            "code": "INPUT_INVALID",
            "node_id": None,
            "field": ".".join(map(str, e["loc"][1:])),
            "message": e["msg"],
        }
        for e in error.errors()
    ]
    message = "; ".join(f"{e['field']}: {e['message']}" for e in fields)
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "INPUT_INVALID", "message": message, "errors": fields}},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "The database could not complete the request. Try again shortly.",
            }
        },
    )


def record(row, exclude=()):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in exclude}


def scoped(db, model, resource_id, p, lock=False):
    try:
        UUID(resource_id)
    except (ValueError, TypeError):
        fail(404, "NOT_FOUND", "The requested item was not found.")
    query = select(model).where(model.id == resource_id, model.workspace_id == p.workspace.id)
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        fail(404, "NOT_FOUND", "The requested item was not found in this workspace.")
    return row


def workflow_view(row):
    result = record(row, ("webhook_token_hash", "webhook_secret"))
    result["webhook_enabled"] = bool(row.webhook_token_hash)
    return result


def user_view(db, user):
    workspaces = db.execute(
        select(Workspace, Member.role, Organization.name)
        .join(Member, Member.organization_id == Workspace.organization_id)
        .join(Organization, Organization.id == Workspace.organization_id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.created_at)
    ).all()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "workspaces": [
            {**record(w), "role": role, "organization_name": org} for w, role, org in workspaces
        ],
    }


@app.get("/api/v1/auth/status")
def auth_status(db: Session = Depends(get_db)):
    return {"setup_required": not db.scalar(select(User.id).limit(1))}


@app.post("/api/v1/auth/setup")
def setup(data: S.MemberInput, request: Request, response: Response, db: Session = Depends(get_db)):
    origin_check(request)
    token = request.headers.get("x-setup-token", "")
    if not settings().setup_token or not secrets.compare_digest(token, settings().setup_token):
        fail(403, "SETUP_DENIED", "Enter the instance setup token.")
    db.execute(text("SELECT pg_advisory_xact_lock(8023471)"))
    if db.scalar(select(User.id).limit(1)):
        fail(409, "SETUP_COMPLETE", "This instance already has an owner.")
    user = User(
        id=uid(),
        email=str(data.email).lower(),
        display_name=data.display_name,
        password_hash=passwords.hash(data.password),
    )
    org = Organization(id=uid(), name="My organization", slug="default")
    db.add_all([user, org])
    db.flush()
    workspace = Workspace(
        id=uid(), organization_id=org.id, name="My workspace", environment="development"
    )
    db.add_all([workspace, Member(organization_id=org.id, user_id=user.id, role="owner")])
    db.flush()
    make_session(db, user.id, response)
    audit(db, Principal(user.id, workspace, "owner"), "instance.created", org.id)
    db.commit()
    return user_view(db, user)


@app.post("/api/v1/auth/login")
def login(data: S.Login, request: Request, response: Response, db: Session = Depends(get_db)):
    origin_check(request)
    limiter("login:" + str(request.client.host), 30, 300)
    limiter("login:email:" + str(data.email).lower(), 10, 300)
    user = db.scalar(
        select(User).where(User.email == str(data.email).lower(), User.is_active.is_(True))
    )
    dummy = "$argon2id$v=19$m=65536,t=3,p=4$ZHVtbXlzYWx0MTIzNDU2Nw$R6oMdOY2nlVAZjRRhBpDeWkrdWmlqhNhCyhkOGBYUq8"
    try:
        passwords.verify(user.password_hash if user else dummy, data.password)
    except (VerifyMismatchError, InvalidHashError):
        fail(401, "LOGIN_FAILED", "Email or password is incorrect.")
    if not user:
        fail(401, "LOGIN_FAILED", "Email or password is incorrect.")
    if passwords.check_needs_rehash(user.password_hash):
        user.password_hash = passwords.hash(data.password)
    make_session(db, user.id, response)
    workspace = db.scalar(
        select(Workspace)
        .join(Member, Member.organization_id == Workspace.organization_id)
        .where(Member.user_id == user.id)
        .limit(1)
    )
    if workspace:
        audit(db, Principal(user.id, workspace, "viewer"), "auth.login", user.id)
    db.commit()
    return user_view(db, user)


@app.post("/api/v1/auth/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    origin_check(request)
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_hash == digest(request.cookies.get("ob_refresh", "")))
        .with_for_update()
    )
    if not session or session.refresh_expires_at <= now():
        fail(401, "AUTH_REQUIRED", "Sign in to continue.")
    if not secrets.compare_digest(
        digest(request.headers.get("x-csrf-token", "")), session.csrf_hash
    ):
        fail(403, "CSRF_FAILED", "Refresh this page and try again.")
    user = db.get(User, session.user_id)
    if not user.is_active:
        fail(401, "AUTH_REQUIRED", "This account is disabled.")
    make_session(db, session.user_id, response, session)
    db.commit()
    return {"refreshed": True}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session = cookie_session(db, request)
    db.delete(session)
    db.commit()
    for name, path in [("ob_session", "/"), ("ob_refresh", "/api/v1/auth"), ("ob_csrf", "/")]:
        response.delete_cookie(name, path=path)
    return {"logged_out": True}


@app.post("/api/v1/auth/logout-all")
def logout_all(p=Depends(require()), db: Session = Depends(get_db)):
    db.execute(delete(AuthSession).where(AuthSession.user_id == p.user_id))
    audit(db, p, "auth.logout_all", p.user_id)
    db.commit()
    return {"logged_out": True}


@app.get("/api/v1/auth/me")
def me(p=Depends(principal), db: Session = Depends(get_db)):
    if p.scopes is not None:
        fail(403, "FORBIDDEN", "Use a user session for profile access.")
    return user_view(db, db.get(User, p.user_id))


def send_reset(email, token):
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = (
        settings().smtp_from,
        email,
        "Reset your OxyBridge password",
    )
    message.set_content(
        f"Reset your password within 15 minutes:\n{settings().app_base_url}/reset-password?token={token}\n\nIgnore this email if you did not request a reset."
    )
    try:
        with smtplib.SMTP(settings().smtp_host, settings().smtp_port, timeout=10) as server:
            if settings().smtp_starttls:
                server.starttls(context=ssl.create_default_context())
            if settings().smtp_user:
                server.login(settings().smtp_user, settings().smtp_password)
            server.send_message(message)
    except Exception:
        log("auth.reset_delivery_failed")


@app.post("/api/v1/auth/forgot-password")
def forgot(
    data: S.EmailInput, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    origin_check(request)
    limiter("reset:" + str(request.client.host), 5, 900)
    user = db.scalar(
        select(User).where(User.email == str(data.email).lower(), User.is_active.is_(True))
    )
    if user and settings().smtp_host:
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordReset(
                user_id=user.id, token_hash=digest(token), expires_at=now() + timedelta(minutes=15)
            )
        )
        db.commit()
        background.add_task(send_reset, user.email, token)
    return {
        "message": "If the account exists and email delivery is configured, a reset link will be sent."
    }


@app.post("/api/v1/auth/reset-password")
def reset_password(data: S.ResetInput, request: Request, db: Session = Depends(get_db)):
    origin_check(request)
    limiter("reset-submit:" + str(request.client.host), 10, 900)
    reset = db.scalar(
        select(PasswordReset)
        .where(PasswordReset.token_hash == digest(data.token), PasswordReset.used.is_(False))
        .with_for_update()
    )
    if not reset or reset.expires_at <= now():
        fail(400, "RESET_INVALID", "The reset link is expired or invalid.")
    user = db.get(User, reset.user_id)
    user.password_hash = passwords.hash(data.password)
    reset.used = True
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}


@app.get("/api/v1/workflows")
def workflows(
    search: str = "",
    status: str = "",
    limit: int = 100,
    offset: int = 0,
    p=Depends(require(scope="workflows:read")),
    db: Session = Depends(get_db),
):
    query = select(Workflow).where(Workflow.workspace_id == p.workspace.id)
    if search:
        query = query.where(Workflow.name.ilike("%" + search[:120] + "%"))
    if status:
        query = query.where(Workflow.status == status)
    else:
        query = query.where(Workflow.status != "ARCHIVED")
    items = db.scalars(
        query.order_by(Workflow.updated_at.desc())
        .limit(min(200, max(1, limit)))
        .offset(max(0, offset))
    ).all()
    result = []
    for workflow in items:
        view = workflow_view(workflow)
        version = (
            db.get(Version, workflow.active_version_id) if workflow.active_version_id else None
        )
        view["version_number"] = version.number if version else None
        latest = db.scalar(
            select(Run)
            .where(Run.workflow_id == workflow.id)
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        view["last_run"] = (
            record(latest, ("encrypted_payload", "trace_context")) if latest else None
        )
        counts = dict(
            db.execute(
                select(Run.status, func.count())
                .where(Run.workflow_id == workflow.id, Run.created_at > now() - timedelta(days=7))
                .group_by(Run.status)
            ).all()
        )
        total = counts.get("SUCCEEDED", 0) + counts.get("FAILED", 0) + counts.get("TIMED_OUT", 0)
        view["success_rate"] = round(counts.get("SUCCEEDED", 0) * 100 / total, 1) if total else None
        result.append(view)
    return result


@app.post("/api/v1/workflows", status_code=201)
def add_workflow(
    data: S.WorkflowInput, p=Depends(require("editor")), db: Session = Depends(get_db)
):
    definition = data.definition.model_dump(mode="json")
    if len(json.dumps(definition)) > 1_000_000:
        fail(413, "WORKFLOW_TOO_LARGE", "The workflow definition exceeds 1 MB.")
    workflow = Workflow(
        id=uid(),
        workspace_id=p.workspace.id,
        name=data.name.strip(),
        description=data.description,
        definition=definition,
        created_by=p.user_id,
    )
    db.add(workflow)
    audit(db, p, "workflow.created", workflow.id)
    db.commit()
    return workflow_view(workflow)


@app.get("/api/v1/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str, p=Depends(require(scope="workflows:read")), db: Session = Depends(get_db)
):
    return workflow_view(scoped(db, Workflow, workflow_id, p))


@app.patch("/api/v1/workflows/{workflow_id}")
def edit_workflow(
    workflow_id: str,
    data: S.DraftInput,
    p=Depends(require("editor")),
    db: Session = Depends(get_db),
):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    if workflow.revision != data.expected_revision:
        fail(
            409,
            "REVISION_CONFLICT",
            "This draft changed in another tab. Export your edits, then reload the latest draft.",
        )
    if workflow.status == "ARCHIVED":
        fail(409, "WORKFLOW_ARCHIVED", "Restore the workflow before editing it.")
    for key in ("name", "description", "definition"):
        value = getattr(data, key)
        if value is not None:
            if key == "definition":
                value = value.model_dump(mode="json")
            setattr(workflow, key, value)
    workflow.revision += 1
    workflow.updated_at = now()
    audit(db, p, "workflow.edited", workflow.id, {"revision": workflow.revision})
    db.commit()
    return workflow_view(workflow)


@app.delete("/api/v1/workflows/{workflow_id}")
def archive_workflow(workflow_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    workflow.status = "ARCHIVED"
    workflow.updated_at = now()
    audit(db, p, "workflow.archived", workflow.id)
    db.commit()
    return {"archived": True}


def validation(db, workflow):
    credentials = {
        c.id: c
        for c in db.scalars(
            select(Connection).where(Connection.workspace_id == workflow.workspace_id)
        ).all()
    }
    return validate(workflow.definition, credentials)


@app.post("/api/v1/workflows/{workflow_id}/validate")
def check_workflow(workflow_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    return validation(db, scoped(db, Workflow, workflow_id, p))


def publish_version(db, workflow, user_id, is_test=False):
    result = validation(db, workflow)
    if not result["valid"]:
        raise HTTPException(
            422,
            detail={
                "code": "WORKFLOW_INVALID",
                "message": "Fix workflow validation errors before publishing.",
                "errors": result["errors"],
            },
        )
    number = (
        db.scalar(select(func.max(Version.number)).where(Version.workflow_id == workflow.id)) or 0
    ) + 1
    version = Version(
        id=uid(),
        workflow_id=workflow.id,
        number=number,
        definition=json.loads(json.dumps(workflow.definition)),
        definition_hash=content_hash(workflow.definition),
        published_by=user_id,
        is_test=is_test,
    )
    db.add(version)
    db.flush()
    return version


@app.post("/api/v1/workflows/{workflow_id}/publish")
def publish(workflow_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    version = publish_version(db, workflow, p.user_id)
    workflow.active_version_id, workflow.status = version.id, "ACTIVE"
    workflow.updated_at = now()
    audit(db, p, "workflow.published", workflow.id, {"version": version.number})
    db.commit()
    return {"workflow": workflow_view(workflow), "version": record(version)}


@app.post("/api/v1/workflows/{workflow_id}/pause")
def pause(workflow_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    if workflow.status != "ACTIVE":
        fail(409, "WORKFLOW_DISABLED", "Only active workflows can be paused.")
    workflow.status = "PAUSED"
    audit(db, p, "workflow.paused", workflow.id)
    db.commit()
    return workflow_view(workflow)


@app.post("/api/v1/workflows/{workflow_id}/resume")
def resume(workflow_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    if not workflow.active_version_id and workflow.status != "ARCHIVED":
        fail(409, "WORKFLOW_INVALID", "Publish a version before enabling this workflow.")
    workflow.status = "ACTIVE" if workflow.active_version_id else "DRAFT"
    audit(db, p, "workflow.resumed", workflow.id)
    db.commit()
    return workflow_view(workflow)


@app.get("/api/v1/workflows/{workflow_id}/versions")
def versions(
    workflow_id: str, p=Depends(require(scope="workflows:read")), db: Session = Depends(get_db)
):
    scoped(db, Workflow, workflow_id, p)
    return [
        record(v)
        for v in db.scalars(
            select(Version)
            .where(Version.workflow_id == workflow_id)
            .order_by(Version.number.desc())
            .limit(100)
        ).all()
    ]


@app.get("/api/v1/workflows/{workflow_id}/export")
def export_workflow(
    workflow_id: str, p=Depends(require(scope="workflows:read")), db: Session = Depends(get_db)
):
    workflow = scoped(db, Workflow, workflow_id, p)
    return {
        "format": "OxyBridge-workflow",
        "format_version": 1,
        "workflow": {
            "name": workflow.name,
            "description": workflow.description,
            "definition": redact(workflow.definition),
        },
        "required_connections": sorted(
            {
                n.get("config", {}).get("connection_id")
                for n in workflow.definition.get("nodes", [])
                if n.get("config", {}).get("connection_id")
            }
        ),
    }


@app.post("/api/v1/workflows/{workflow_id}/run", status_code=202)
def run_workflow(
    workflow_id: str,
    data: S.RunInput,
    request: Request,
    background: BackgroundTasks,
    p=Depends(require("editor", "runs:write")),
    db: Session = Depends(get_db),
):
    limiter("run:" + p.workspace.id, 120)
    workflow = scoped(db, Workflow, workflow_id, p, True)
    version = publish_version(db, workflow, p.user_id, True) if data.test else None
    if data.test and p.scopes is not None:
        fail(403, "FORBIDDEN", "API keys can execute published versions only.")
    key = request.headers.get("idempotency-key") or data.idempotency_key
    if key and len(key) > 200:
        fail(400, "IDEMPOTENCY_INVALID", "Idempotency keys must be at most 200 characters.")
    run = create_run(
        db,
        workflow,
        data.payload,
        "test" if data.test else "api" if p.scopes is not None else "manual",
        key,
        version.id if version else None,
        trigger_metadata={"headers": dict(request.headers), "query": dict(request.query_params)},
    )
    audit(db, p, "run.started", run.id)
    db.commit()
    background.add_task(drain, run.id)
    return {"run_id": run.id, "status": run.status}


def validate_secret(kind, secret):
    required = {
        "bearer": ["token"],
        "api_key": ["token", "header"],
        "basic": ["username", "password"],
        "postgres": ["host", "database", "username", "password"],
    }[kind]
    if any(
        not isinstance(secret.get(k), str) or not secret[k] or len(secret[k]) > 4096
        for k in required
    ):
        fail(422, "CREDENTIAL_INVALID", "Enter all required credential fields.")
    if kind == "api_key" and (
        not __import__("re").fullmatch(r"[A-Za-z0-9-]+", secret["header"])
        or secret["header"].lower() in {"host", "content-length", "cookie", "connection"}
    ):
        fail(422, "CREDENTIAL_INVALID", "Use a valid API key header name.")
    if kind == "postgres" and secret.get("sslmode", "require") not in {
        "require",
        "verify-ca",
        "verify-full",
        "disable",
    }:
        fail(422, "CREDENTIAL_INVALID", "Select a supported database SSL mode.")


def connection_view(connection):
    return record(connection, ("encrypted_secret",))


def approved_hosts(kind, hosts):
    import ipaddress
    import re

    if kind == "postgres":
        return []
    if not hosts:
        fail(
            422,
            "CREDENTIAL_SCOPE_REQUIRED",
            "Approve at least one API hostname for this credential.",
        )
    result = []
    for value in hosts:
        host = value.lower().rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                fail(
                    422,
                    "CREDENTIAL_SCOPE_INVALID",
                    "Use exact hostnames without schemes, paths, ports or wildcards.",
                )
        result.append(host)
    return sorted(set(result))


@app.get("/api/v1/connections")
def connections(p=Depends(require()), db: Session = Depends(get_db)):
    return [
        connection_view(c)
        for c in db.scalars(
            select(Connection)
            .where(Connection.workspace_id == p.workspace.id)
            .order_by(Connection.created_at.desc())
        ).all()
    ]


@app.post("/api/v1/connections", status_code=201)
def add_connection(
    data: S.ConnectionInput, p=Depends(require("admin")), db: Session = Depends(get_db)
):
    validate_secret(data.type, data.secret)
    hosts = approved_hosts(data.type, data.allowed_hosts)
    connection = Connection(
        id=uid(),
        workspace_id=p.workspace.id,
        name=data.name,
        type=data.type,
        encrypted_secret=encrypt(data.secret),
        allow_writes=data.allow_writes,
        config={"allowed_hosts": hosts},
    )
    db.add(connection)
    audit(db, p, "connection.created", connection.id)
    db.commit()
    return connection_view(connection)


@app.patch("/api/v1/connections/{connection_id}")
def edit_connection(
    connection_id: str,
    data: S.ConnectionPatch,
    p=Depends(require("admin")),
    db: Session = Depends(get_db),
):
    connection = scoped(db, Connection, connection_id, p, True)
    if data.allowed_hosts is not None:
        connection.config = {"allowed_hosts": approved_hosts(connection.type, data.allowed_hosts)}
    for key in ("name", "enabled", "allow_writes"):
        if getattr(data, key) is not None:
            setattr(connection, key, getattr(data, key))
    if data.secret is not None:
        validate_secret(connection.type, data.secret)
        connection.encrypted_secret = encrypt(data.secret)
        connection.test_status = None
        audit(db, p, "connection.secret_replaced", connection.id)
    audit(db, p, "connection.updated", connection.id)
    db.commit()
    return connection_view(connection)


@app.delete("/api/v1/connections/{connection_id}")
def remove_connection(
    connection_id: str, p=Depends(require("admin")), db: Session = Depends(get_db)
):
    connection = scoped(db, Connection, connection_id, p, True)
    # Retain the row for historical references; deleting the encrypted secret revokes it immediately.
    connection.enabled, connection.encrypted_secret = False, encrypt({})
    audit(db, p, "connection.deleted", connection.id)
    db.commit()
    return {"disabled": True}


@app.post("/api/v1/connections/{connection_id}/test")
def test_connection(connection_id: str, p=Depends(require("admin")), db: Session = Depends(get_db)):
    connection = scoped(db, Connection, connection_id, p)
    if not connection.enabled:
        fail(409, "CREDENTIAL_UNAVAILABLE", "Enable the connection before testing it.")
    secret = decrypt(connection.encrypted_secret)
    try:
        validate_secret(connection.type, secret)
        if connection.type == "postgres":
            from oxybridge.nodes import postgres_query

            postgres_query({"query": "SELECT 1 AS connected", "mode": "read"}, {}, secret)
            message = "Database connection succeeded."
        else:
            message = "Credential format is valid. Test authentication by running an HTTP node against your provider."
        connection.test_status = "VALID"
    except (NodeError, HTTPException):
        connection.test_status, message = (
            "FAILED",
            "Connection validation failed. Check the fields, network policy and provider access.",
        )
    connection.tested_at = now()
    audit(db, p, "connection.tested", connection.id)
    db.commit()
    return {"status": connection.test_status, "message": message}


@app.post("/api/v1/schedules/preview")
def preview_schedule(data: S.SchedulePreview, p=Depends(require("editor"))):
    try:
        return {"next_runs": next_times(data.cron, data.timezone, now())}
    except Exception:
        fail(422, "SCHEDULE_INVALID", "Enter a valid five-field cron expression and IANA timezone.")


@app.get("/api/v1/schedules")
def schedules(p=Depends(require()), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Schedule, Workflow.name)
        .join(Workflow, Workflow.id == Schedule.workflow_id)
        .where(Schedule.workspace_id == p.workspace.id)
        .order_by(Schedule.next_run_at)
    ).all()
    return [{**record(s), "workflow_name": name} for s, name in rows]


@app.post("/api/v1/schedules", status_code=201)
def add_schedule(
    data: S.ScheduleInput, p=Depends(require("editor")), db: Session = Depends(get_db)
):
    workflow = scoped(db, Workflow, data.workflow_id, p)
    if workflow.status != "ACTIVE":
        fail(409, "WORKFLOW_DISABLED", "Publish and enable the workflow before adding a schedule.")
    try:
        next_run = next_times(data.cron, data.timezone, now(), 1)[0]
    except Exception:
        fail(422, "SCHEDULE_INVALID", "Enter a valid five-field cron expression and IANA timezone.")
    schedule = Schedule(
        id=uid(),
        workspace_id=p.workspace.id,
        workflow_id=workflow.id,
        cron=data.cron,
        timezone=data.timezone,
        enabled=data.enabled,
        next_run_at=next_run,
    )
    db.add(schedule)
    audit(db, p, "schedule.created", schedule.id)
    db.commit()
    return record(schedule)


@app.patch("/api/v1/schedules/{schedule_id}")
def edit_schedule(
    schedule_id: str,
    data: S.EnabledInput,
    p=Depends(require("editor")),
    db: Session = Depends(get_db),
):
    schedule = scoped(db, Schedule, schedule_id, p, True)
    schedule.enabled = data.enabled
    if data.enabled:
        schedule.next_run_at = next_times(schedule.cron, schedule.timezone, now(), 1)[0]
    audit(db, p, "schedule.updated", schedule.id)
    db.commit()
    return record(schedule)


@app.delete("/api/v1/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    schedule = scoped(db, Schedule, schedule_id, p, True)
    db.delete(schedule)
    audit(db, p, "schedule.deleted", schedule_id)
    db.commit()
    return {"deleted": True}


@app.get("/api/v1/dead-letters")
def dead_letters(p=Depends(require()), db: Session = Depends(get_db)):
    rows = db.execute(
        select(DeadLetter, Workflow.name, NodeRun.label, NodeRun.attempt)
        .join(Run, Run.id == DeadLetter.run_id)
        .join(Workflow, Workflow.id == Run.workflow_id)
        .outerjoin(NodeRun, NodeRun.id == DeadLetter.node_run_id)
        .where(DeadLetter.workspace_id == p.workspace.id)
        .order_by(DeadLetter.created_at.desc())
        .limit(200)
    ).all()
    return [
        {**record(item), "workflow_name": name, "node_label": label, "attempts": attempts}
        for item, name, label, attempts in rows
    ]


@app.post("/api/v1/dead-letters/{item_id}/resolve")
def resolve_dead_letter(item_id: str, p=Depends(require("editor")), db: Session = Depends(get_db)):
    item = scoped(db, DeadLetter, item_id, p, True)
    item.resolved_at, item.resolved_by = now(), p.user_id
    audit(db, p, "dead_letter.resolved", item.id)
    db.commit()
    return record(item)


@app.get("/api/v1/audit")
def audit_log(p=Depends(require("admin")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Audit, User.display_name)
        .outerjoin(User, User.id == Audit.actor_user_id)
        .where(Audit.workspace_id == p.workspace.id)
        .order_by(Audit.created_at.desc())
        .limit(200)
    ).all()
    return [{**record(item), "actor": name or "System"} for item, name in rows]


@app.get("/api/v1/api-keys")
def api_keys(p=Depends(require("admin")), db: Session = Depends(get_db)):
    return [
        record(k, ("key_hash",))
        for k in db.scalars(
            select(ApiKey)
            .where(ApiKey.workspace_id == p.workspace.id)
            .order_by(ApiKey.created_at.desc())
        ).all()
    ]


@app.post("/api/v1/api-keys", status_code=201)
def create_key(data: S.KeyInput, p=Depends(require("admin")), db: Session = Depends(get_db)):
    token = "ob_" + secrets.token_urlsafe(32)
    key = ApiKey(
        id=uid(),
        workspace_id=p.workspace.id,
        created_by=p.user_id,
        name=data.name,
        key_prefix=token[:12],
        key_hash=digest(token),
        scopes=data.scopes,
        expires_at=now() + timedelta(days=data.expires_days),
    )
    db.add(key)
    audit(db, p, "api_key.created", key.id)
    db.commit()
    return {**record(key, ("key_hash",)), "token": token}


@app.delete("/api/v1/api-keys/{key_id}")
def revoke_key(key_id: str, p=Depends(require("admin")), db: Session = Depends(get_db)):
    key = scoped(db, ApiKey, key_id, p, True)
    key.revoked_at = now()
    audit(db, p, "api_key.revoked", key.id)
    db.commit()
    return {"revoked": True}


@app.get("/api/v1/members")
def members(p=Depends(require("admin")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(User, Member.role)
        .join(Member, Member.user_id == User.id)
        .where(Member.organization_id == p.workspace.organization_id)
    ).all()
    return [
        {"id": user.id, "display_name": user.display_name, "email": user.email, "role": role}
        for user, role in rows
    ]


@app.post("/api/v1/members", status_code=201)
def add_member(data: S.MemberInput, p=Depends(require("admin")), db: Session = Depends(get_db)):
    if data.role == "admin" and p.role != "owner":
        fail(403, "FORBIDDEN", "Only the owner can add administrators.")
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user:
        fail(
            409,
            "MEMBER_EXISTS",
            "This email already has an account. Use the local administrator command to manage existing memberships.",
        )
    user = User(
        id=uid(),
        email=str(data.email).lower(),
        display_name=data.display_name,
        password_hash=passwords.hash(data.password),
    )
    db.add(user)
    db.flush()
    db.add(Member(organization_id=p.workspace.organization_id, user_id=user.id, role=data.role))
    audit(db, p, "member.added", user.id, {"role": data.role})
    db.commit()
    return {"id": user.id, "email": user.email, "role": data.role}


@app.patch("/api/v1/members/{user_id}")
def change_role(
    user_id: str, data: S.RoleInput, p=Depends(require("owner")), db: Session = Depends(get_db)
):
    member = db.get(Member, (p.workspace.organization_id, user_id))
    if not member or member.role == "owner":
        fail(403, "FORBIDDEN", "The owner role cannot be changed here.")
    member.role = data.role
    db.execute(
        delete(ApiKey).where(
            ApiKey.created_by == user_id,
            ApiKey.workspace_id.in_(
                select(Workspace.id).where(Workspace.organization_id == p.workspace.organization_id)
            ),
        )
    )
    audit(db, p, "member.role_changed", user_id, {"role": data.role})
    db.commit()
    return {"role": data.role}


@app.delete("/api/v1/members/{user_id}")
def remove_member(user_id: str, p=Depends(require("owner")), db: Session = Depends(get_db)):
    member = db.get(Member, (p.workspace.organization_id, user_id))
    if not member or member.role == "owner":
        fail(403, "FORBIDDEN", "The owner cannot be removed.")
    db.delete(member)
    db.execute(
        delete(ApiKey).where(
            ApiKey.created_by == user_id,
            ApiKey.workspace_id.in_(
                select(Workspace.id).where(Workspace.organization_id == p.workspace.organization_id)
            ),
        )
    )
    audit(db, p, "member.removed", user_id)
    db.commit()
    return {"removed": True}


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(
    data: S.WorkspaceInput, p=Depends(require("admin")), db: Session = Depends(get_db)
):
    workspace = Workspace(
        id=uid(),
        organization_id=p.workspace.organization_id,
        name=data.name,
        environment=data.environment,
    )
    db.add(workspace)
    audit(db, p, "workspace.created", workspace.id)
    db.commit()
    return record(workspace)


@app.patch("/api/v1/settings")
def update_settings(
    data: S.SettingsInput, p=Depends(require("admin")), db: Session = Depends(get_db)
):
    workspace = db.scalar(select(Workspace).where(Workspace.id == p.workspace.id).with_for_update())
    workspace.name, workspace.retention_days = data.name, data.retention_days
    audit(db, p, "workspace.updated", workspace.id)
    db.commit()
    return record(workspace)


@app.get("/api/v1/dashboard")
def dashboard(p=Depends(require()), db: Session = Depends(get_db)):
    day = now() - timedelta(hours=24)
    rows = db.scalars(
        select(Run)
        .where(Run.workspace_id == p.workspace.id, Run.created_at >= day)
        .order_by(Run.created_at)
    ).all()
    counts = Counter(r.status for r in rows)
    terminal = counts["SUCCEEDED"] + counts["FAILED"] + counts["TIMED_OUT"]
    durations = sorted(r.duration_ms for r in rows if r.duration_ms is not None)
    hours = []
    start = now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    for i in range(24):
        hour = start + timedelta(hours=i)
        batch = [r for r in rows if hour <= r.created_at < hour + timedelta(hours=1)]
        values = sorted(r.duration_ms for r in batch if r.duration_ms is not None)
        hours.append(
            {
                "time": hour.isoformat(),
                "succeeded": sum(r.status == "SUCCEEDED" for r in batch),
                "failed": sum(r.status in {"FAILED", "TIMED_OUT"} for r in batch),
                "total": len(batch),
                "latency_ms": values[min(len(values) - 1, int(len(values) * 0.95))]
                if values
                else 0,
            }
        )
    active = db.scalar(
        select(func.count())
        .select_from(Workflow)
        .where(Workflow.workspace_id == p.workspace.id, Workflow.status == "ACTIVE")
    )
    queued = db.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.workspace_id == p.workspace.id,
            Run.status.in_(["QUEUED", "RUNNING", "CANCEL_REQUESTED"]),
        )
    )
    recent = db.scalars(
        select(Run)
        .where(Run.workspace_id == p.workspace.id)
        .order_by(Run.created_at.desc())
        .limit(6)
    ).all()
    return {
        "runs_today": len(rows),
        "active_workflows": active,
        "success_rate": round(counts["SUCCEEDED"] * 100 / terminal, 1) if terminal else None,
        "failed_runs": counts["FAILED"] + counts["TIMED_OUT"],
        "queued": queued,
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
        "p95_duration_ms": durations[min(len(durations) - 1, int(len(durations) * 0.95))]
        if durations
        else None,
        "hours": hours,
        "recent_runs": [run_view(db, r) for r in recent],
        "health": {
            "database": "healthy",
            "runtime": "ASGI",
            "services": [record(h) for h in db.scalars(select(Heartbeat)).all()],
        },
    }


@app.get("/api/v1/templates")
def templates(p=Depends(require())):
    from oxybridge.templates import templates

    return templates()


@app.get("/api/v1/system/info")
def system_info(p=Depends(require())):
    return {
        "version": "0.1.0",
        "runtime": "ASGI",
        "database": "PostgreSQL",
        "queue": "PostgreSQL durable outbox",
        "scheduled_execution": "Continuous scheduler process or authenticated scheduler tick",
        "email_configured": bool(settings().smtp_host),
        "max_nodes": 200,
        "max_http_timeout": 120,
        "max_run_seconds": settings().run_max_seconds,
    }


@app.get("/api/v1/system/tick")
def tick(request: Request):
    expected = settings().cron_secret
    supplied = request.headers.get("authorization", "")
    if not expected or not secrets.compare_digest(supplied, "Bearer " + expected):
        fail(401, "AUTH_REQUIRED", "A valid cron credential is required.")
    recover_once()
    schedule_once()
    processed = drain(budget=settings().execution_budget_seconds)
    retention_once()
    return {"processed_events": processed, "at": now()}


@app.get("/health/live")
def live():
    return {"status": "alive", "version": "0.1.0"}


@app.get("/health/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM alembic_version"))
        return {"status": "ready", "database": "healthy"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable_or_unmigrated"},
        )


@app.get("/metrics")
def metrics(request: Request):
    if settings().app_env in {"staging", "production"} and not secrets.compare_digest(
        request.headers.get("authorization", ""), "Bearer " + settings().cron_secret
    ):
        fail(401, "AUTH_REQUIRED", "A monitoring credential is required.")
    lines = []
    with DBSession() as db:
        for status, count in db.execute(
            select(Run.status, func.count()).group_by(Run.status)
        ).all():
            lines.append(f'oxybridge_runs{{status="{status}"}} {count}')
        pending = db.scalar(
            select(func.count()).select_from(Outbox).where(Outbox.published_at.is_(None))
        )
        failed = db.scalar(
            select(func.count()).select_from(DeadLetter).where(DeadLetter.resolved_at.is_(None))
        )
        retries = db.scalar(select(func.sum(NodeRun.attempt - 1)).where(NodeRun.attempt > 1)) or 0
        lines.extend(
            [
                f"oxybridge_outbox_pending {pending}",
                f"oxybridge_dead_letters_unresolved {failed}",
                f"oxybridge_node_retries {retries}",
            ]
        )
    return Response(
        content=generate_latest() + ("\n".join(lines) + "\n").encode(),
        media_type="text/plain; version=0.0.4",
    )


def run_view(db, run, detail=False):
    result = record(run, ("encrypted_payload", "trace_context"))
    workflow, version = db.get(Workflow, run.workflow_id), db.get(Version, run.version_id)
    result.update(
        workflow_name=workflow.name, version_number=version.number, is_test=version.is_test
    )
    nodes = db.scalars(
        select(NodeRun).where(NodeRun.run_id == run.id).order_by(NodeRun.created_at)
    ).all()
    result["retries"] = sum(max(0, n.attempt - 1) for n in nodes)
    if detail:
        result["definition"] = version.definition
        result["nodes"] = [
            {
                **record(n, ("encrypted_output", "claim_token", "lease_until")),
                "attempts": [
                    record(a)
                    for a in db.scalars(
                        select(Attempt).where(Attempt.node_run_id == n.id).order_by(Attempt.number)
                    ).all()
                ],
            }
            for n in nodes
        ]
    return result


@app.get("/api/v1/workflow-runs")
def runs(
    status: str = "",
    workflow_id: str = "",
    search: str = "",
    trigger: str = "",
    since: str = "",
    limit: int = 50,
    offset: int = 0,
    p=Depends(require(scope="runs:read")),
    db: Session = Depends(get_db),
):
    query = select(Run).where(Run.workspace_id == p.workspace.id)
    if status:
        query = query.where(Run.status == status)
    if workflow_id:
        scoped(db, Workflow, workflow_id, p)
        query = query.where(Run.workflow_id == workflow_id)
    if search:
        query = query.where(
            Run.id.cast(__import__("sqlalchemy").String).ilike("%" + search[:100] + "%")
        )
    if trigger:
        query = query.where(Run.trigger_type == trigger)
    if since:
        try:
            query = query.where(Run.created_at >= datetime.fromisoformat(since).replace(tzinfo=UTC))
        except ValueError:
            fail(400, "DATE_INVALID", "Use an ISO date for the date filter.")
    return [
        run_view(db, run)
        for run in db.scalars(
            query.order_by(Run.created_at.desc())
            .limit(min(200, max(1, limit)))
            .offset(max(0, offset))
        ).all()
    ]


@app.get("/api/v1/workflow-runs/{run_id}")
def get_run(run_id: str, p=Depends(require(scope="runs:read")), db: Session = Depends(get_db)):
    return run_view(db, scoped(db, Run, run_id, p), True)


@app.post("/api/v1/workflow-runs/{run_id}/advance")
def advance(run_id: str, p=Depends(require("editor", "runs:write")), db: Session = Depends(get_db)):
    run = scoped(db, Run, run_id, p)
    limiter("advance:" + p.workspace.id, 120)
    if run.status not in TERMINAL:
        db.commit()
        recover_once()
        drain(run_id)
        db.expire_all()
    return run_view(db, db.get(Run, run_id), True)


@app.post("/api/v1/workflow-runs/{run_id}/cancel")
def cancel(
    run_id: str,
    background: BackgroundTasks,
    p=Depends(require("editor", "runs:write")),
    db: Session = Depends(get_db),
):
    run = scoped(db, Run, run_id, p, True)
    if run.status not in {"QUEUED", "RUNNING"}:
        fail(409, "RUN_TERMINAL", "Only queued or running executions can be cancelled.")
    transition(run, "CANCELLED" if run.status == "QUEUED" else "CANCEL_REQUESTED")
    if run.status == "CANCEL_REQUESTED":
        enqueue(db, "oxybridge.orchestrate", {"run_id": run.id})
    else:
        for node in db.scalars(select(NodeRun).where(NodeRun.run_id == run.id)).all():
            node.status = "CANCELLED"
    audit(db, p, "run.cancelled", run.id)
    db.commit()
    background.add_task(drain, run.id)
    return {"status": run.status}


@app.post("/api/v1/workflow-runs/{run_id}/rerun", status_code=202)
def rerun(
    run_id: str,
    background: BackgroundTasks,
    p=Depends(require("editor", "runs:write")),
    db: Session = Depends(get_db),
):
    old = scoped(db, Run, run_id, p)
    if p.scopes is not None and db.get(Version, old.version_id).is_test:
        fail(403, "FORBIDDEN", "API keys can only rerun published versions.")
    if old.status not in TERMINAL:
        fail(409, "RUN_ACTIVE", "Wait for the execution to finish before rerunning it.")
    if old.encrypted_payload is None:
        fail(
            409,
            "PAYLOAD_EXPIRED",
            "The original input has expired under retention. Start a new run with fresh input.",
        )
    workflow = scoped(db, Workflow, old.workflow_id, p, True)
    if workflow.status != "ACTIVE":
        fail(409, "WORKFLOW_DISABLED", "Enable the workflow before rerunning it.")
    run = create_run(
        db,
        workflow,
        decrypt(old.encrypted_payload),
        "recovery",
        version_id=old.version_id,
        recovery_of=old.id,
        trigger_metadata=old.trace_context.get("trigger", {}),
    )
    audit(db, p, "run.rerun", run.id, {"recovery_of": old.id})
    db.commit()
    background.add_task(drain, run.id)
    return {"run_id": run.id}


@app.get("/api/v1/workflow-runs/{run_id}/events/stream")
def events(
    run_id: str,
    p=Depends(require(scope="runs:read")),
    db: Session = Depends(get_db),
):
    scoped(db, Run, run_id, p)
    db.close()

    def stream():
        previous, deadline = "", time.monotonic() + 25
        while time.monotonic() < deadline:
            with DBSession() as current:
                run = current.get(Run, run_id)
                data = json.dumps(jsonable_encoder(run_view(current, run, True)))
                finished = run.status in TERMINAL
            # StreamingResponse runs synchronous iteration off the event loop; release DB before yield.
            if data != previous:
                yield f"event: snapshot\ndata: {data}\n\n"
                previous = data
            else:
                yield ": heartbeat\n\n"
            if finished:
                break
            time.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/workflows/{workflow_id}/webhook")
def create_hook(
    workflow_id: str, data: S.HookInput, p=Depends(require("editor")), db: Session = Depends(get_db)
):
    workflow = scoped(db, Workflow, workflow_id, p, True)
    if not any(n.get("type") == "webhook" for n in workflow.definition.get("nodes", [])):
        fail(422, "TRIGGER_INVALID", "Add a webhook trigger before generating an endpoint.")
    token = secrets.token_urlsafe(32)
    workflow.webhook_token_hash = digest(token)
    workflow.webhook_secret = encrypt(data.hmac_secret) if data.hmac_secret else None
    audit(db, p, "webhook.rotated", workflow.id)
    db.commit()
    return {
        "url": settings().app_base_url + f"/hooks/v1/{workflow.id}/{token}",
        "message": "Copy this URL now. Its token is shown only once.",
    }


@app.post("/hooks/v1/{workflow_id}/{token}", status_code=202)
async def hook(
    workflow_id: str,
    token: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    limiter("hook:" + workflow_id, 60)
    try:
        UUID(workflow_id)
    except ValueError:
        fail(404, "NOT_FOUND", "The webhook endpoint was not found.")
    workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    if (
        not workflow
        or not workflow.webhook_token_hash
        or not secrets.compare_digest(digest(token), workflow.webhook_token_hash)
    ):
        fail(401, "TRIGGER_AUTH_FAILED", "Webhook authentication failed.")
    if "application/json" not in request.headers.get("content-type", "").lower():
        fail(415, "CONTENT_TYPE_INVALID", "Send application/json.")
    raw = await request.body()
    if workflow.webhook_secret:
        import hashlib
        import hmac

        timestamp = request.headers.get("x-oxybridge-timestamp", "")
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise ValueError()
        except ValueError:
            fail(401, "TRIGGER_AUTH_FAILED", "Webhook signature timestamp is invalid or expired.")
        expected = hmac.new(
            decrypt(workflow.webhook_secret).encode(),
            timestamp.encode() + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(expected, request.headers.get("x-oxybridge-signature", "")):
            fail(401, "TRIGGER_AUTH_FAILED", "Webhook signature is invalid.")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError()
    except ValueError:
        fail(400, "PAYLOAD_INVALID", "The webhook body must be a JSON object.")
    version = db.get(Version, workflow.active_version_id) if workflow.active_version_id else None
    if not version or not any(n.get("type") == "webhook" for n in version.definition["nodes"]):
        fail(409, "TRIGGER_INVALID", "The active version must use a webhook trigger.")
    key = request.headers.get("idempotency-key")
    if key and len(key) > 200:
        fail(400, "IDEMPOTENCY_INVALID", "Idempotency keys must be at most 200 characters.")
    if workflow.webhook_secret and not key:
        key = "hmac:" + request.headers["x-oxybridge-signature"]
    run = create_run(
        db,
        workflow,
        payload,
        "webhook",
        key,
        trigger_metadata={"headers": dict(request.headers), "query": dict(request.query_params)},
    )
    db.commit()
    background.add_task(drain, run.id)
    return {"run_id": run.id, "status": run.status}


# Keep the SPA fallback after all API routes so missing resources stay 404s.
web_dist = Path(settings().web_dist_dir).resolve()
if (web_dist / "index.html").is_file():
    if (web_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.split("/", 1)[0] in {"api", "hooks", "health", "metrics"} or any(
            part.startswith(".") for part in path.split("/")
        ):
            raise HTTPException(404)
        target = (web_dist / path).resolve()
        if not target.is_relative_to(web_dist):
            raise HTTPException(404)
        if target.is_file():
            return FileResponse(target)
        if Path(path).suffix:
            raise HTTPException(404)
        return FileResponse(web_dist / "index.html", headers={"Cache-Control": "no-cache"})
