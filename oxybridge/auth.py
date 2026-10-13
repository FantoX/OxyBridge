import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from oxybridge.config import settings
from oxybridge.db import get_db, now
from oxybridge.models import ApiKey, Audit, AuthSession, Member, User, Workspace
from oxybridge.security import digest

ROLES = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


@dataclass
class Principal:
    user_id: str
    workspace: Workspace
    role: str
    scopes: list[str] | None = None


def audit(db, principal, action, resource_id=None, details=None):
    db.add(
        Audit(
            organization_id=principal.workspace.organization_id,
            workspace_id=principal.workspace.id,
            actor_user_id=principal.user_id,
            action=action,
            resource_id=resource_id,
            details=details or {},
        )
    )


def origin_check(request: Request):
    origin = request.headers.get("origin")
    if origin and origin not in settings().cors_allowed_origins:
        fail(403, "CSRF_FAILED", "The request origin is not allowed.")


def cookie_session(db, request):
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == digest(request.cookies.get("ob_session", ""))
        )
    )
    if not session or session.expires_at <= now():
        fail(401, "AUTH_REQUIRED", "Sign in to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin_check(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not secrets.compare_digest(digest(csrf), session.csrf_hash):
            fail(403, "CSRF_FAILED", "Refresh this page and try again.")
    return session


def principal(request: Request, db: Session = Depends(get_db)):
    authorization = request.headers.get("authorization", "")
    selected = request.headers.get("x-workspace-id") or request.query_params.get("workspace_id")
    if selected:
        try:
            UUID(selected)
        except ValueError:
            fail(400, "INVALID_WORKSPACE", "Select a valid workspace.")
    if authorization.startswith("Bearer "):
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == digest(authorization[7:])))
        if not key or key.revoked_at or key.expires_at <= now():
            fail(401, "AUTH_REQUIRED", "The API key is invalid or expired.")
        workspace = db.get(Workspace, key.workspace_id)
        if selected and selected != workspace.id:
            fail(403, "FORBIDDEN", "The API key cannot access this workspace.")
        member = db.get(Member, (workspace.organization_id, key.created_by))
        user = db.get(User, key.created_by)
        if not member or not user or not user.is_active:
            fail(403, "FORBIDDEN", "The API key owner no longer has access.")
        key.last_used_at = now()
        db.commit()
        return Principal(key.created_by, workspace, member.role, key.scopes)
    session = cookie_session(db, request)
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        fail(401, "AUTH_REQUIRED", "This account is disabled.")
    query = (
        select(Workspace, Member.role)
        .join(Member, Member.organization_id == Workspace.organization_id)
        .where(Member.user_id == user.id)
    )
    if selected:
        query = query.where(Workspace.id == selected)
    row = db.execute(query.order_by(Workspace.created_at)).first()
    if not row:
        fail(403, "FORBIDDEN", "You do not have access to this workspace.")
    return Principal(user.id, row[0], row[1])


def require(role="viewer", scope=None):
    def dependency(p: Principal = Depends(principal)):
        if ROLES.get(p.role, -1) < ROLES[role]:
            fail(403, "FORBIDDEN", "Your role does not allow this action.")
        if p.scopes is not None and (scope is None or scope not in p.scopes):
            fail(403, "SCOPE_REQUIRED", "The API key does not allow this action.")
        return p

    return dependency


def make_session(db, user_id, response: Response, session=None):
    token, refresh, csrf = (secrets.token_urlsafe(32) for _ in range(3))
    if session is None:
        session = AuthSession(user_id=user_id)
        db.add(session)
    session.token_hash, session.refresh_hash, session.csrf_hash = (
        digest(token),
        digest(refresh),
        digest(csrf),
    )
    session.expires_at = now() + timedelta(minutes=30)
    session.refresh_expires_at = now() + timedelta(days=7)
    for name, value, age, path, http_only in [
        ("ob_session", token, 1800, "/", True),
        ("ob_refresh", refresh, 604800, "/api/v1/auth", True),
        ("ob_csrf", csrf, 604800, "/", False),
    ]:
        response.set_cookie(
            name,
            value,
            max_age=age,
            httponly=http_only,
            secure=settings().session_cookie_secure,
            samesite="lax",
            path=path,
        )
    return session
