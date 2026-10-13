from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from oxybridge.db import Base, now, uid

J = JSON().with_variant(JSONB, "postgresql")
U = UUID(as_uuid=False)


class Identity:
    id: Mapped[str] = mapped_column(U, primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Member(Base):
    __tablename__ = "organization_members"
    organization_id: Mapped[str] = mapped_column(
        U, ForeignKey("organizations.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(U, ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))


class Workspace(Identity, Base):
    __tablename__ = "workspaces"
    organization_id: Mapped[str] = mapped_column(U, ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    environment: Mapped[str] = mapped_column(String(24), default="development")
    retention_days: Mapped[int] = mapped_column(Integer, default=90)


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(U, ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Identity, Base):
    __tablename__ = "password_resets"
    user_id: Mapped[str] = mapped_column(U, ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Workflow(Identity, Base):
    __tablename__ = "workflows"
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict] = mapped_column(
        J, default=lambda: {"schema_version": 1, "nodes": [], "edges": []}
    )
    active_version_id: Mapped[str | None] = mapped_column(
        U,
        ForeignKey("workflow_versions.id", use_alter=True, name="fk_workflow_active_version"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(U, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    webhook_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    webhook_secret: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Version(Identity, Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "number"),)
    workflow_id: Mapped[str] = mapped_column(U, ForeignKey("workflows.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(J)
    definition_hash: Mapped[str] = mapped_column(String(64))
    published_by: Mapped[str] = mapped_column(U, ForeignKey("users.id"))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)


class Run(Identity, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "idempotency_key"),
        Index("ix_runs_workspace_status_created", "workspace_id", "status", "created_at"),
    )
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"))
    workflow_id: Mapped[str] = mapped_column(U, ForeignKey("workflows.id"), index=True)
    version_id: Mapped[str] = mapped_column(U, ForeignKey("workflow_versions.id"))
    trigger_type: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    trigger_payload: Mapped[dict] = mapped_column(J)
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_of: Mapped[str | None] = mapped_column(
        U, ForeignKey("workflow_runs.id"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_context: Mapped[dict] = mapped_column(J, default=dict)


class NodeRun(Identity, Base):
    __tablename__ = "node_runs"
    __table_args__ = (UniqueConstraint("run_id", "node_id"),)
    run_id: Mapped[str] = mapped_column(U, ForeignKey("workflow_runs.id"), index=True)
    node_id: Mapped[str] = mapped_column(U)
    node_type: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    input_data: Mapped[dict | None] = mapped_column(J, nullable=True)
    output_data: Mapped[dict | list | str | int | bool | None] = mapped_column(J, nullable=True)
    encrypted_output: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(24), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(U, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    queue: Mapped[str] = mapped_column(String(24), default="default")


class Attempt(Identity, Base):
    __tablename__ = "node_attempts"
    __table_args__ = (UniqueConstraint("node_run_id", "number"),)
    node_run_id: Mapped[str] = mapped_column(U, ForeignKey("node_runs.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Connection(Identity, Base):
    __tablename__ = "connections"
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict] = mapped_column(J, default=dict)
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_writes: Mapped[bool] = mapped_column(Boolean, default=False)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Schedule(Identity, Base):
    __tablename__ = "schedules"
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(U, ForeignKey("workflows.id"))
    cron: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Outbox(Identity, Base):
    __tablename__ = "outbox_events"
    task: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(J)
    queue: Mapped[str] = mapped_column(String(24))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(U, nullable=True)
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeadLetter(Identity, Base):
    __tablename__ = "dead_letter_items"
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(U, ForeignKey("workflow_runs.id"), unique=True)
    node_run_id: Mapped[str | None] = mapped_column(U, ForeignKey("node_runs.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(U, ForeignKey("users.id"), nullable=True)
    recovery_run_id: Mapped[str | None] = mapped_column(
        U, ForeignKey("workflow_runs.id"), nullable=True
    )


class ApiKey(Identity, Base):
    __tablename__ = "api_keys"
    workspace_id: Mapped[str] = mapped_column(U, ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str] = mapped_column(U, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(J)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Audit(Identity, Base):
    __tablename__ = "audit_logs"
    organization_id: Mapped[str] = mapped_column(U, ForeignKey("organizations.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(U, ForeignKey("workspaces.id"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(U, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(J, default=dict)


class Heartbeat(Base):
    __tablename__ = "service_heartbeats"
    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
