from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from oxybridge.security import connection_references


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "display_name", check_fields=False)
    @classmethod
    def meaningful_name(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Enter a non-empty name")
        return value


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class EmailInput(Input):
    email: EmailStr


class ResetInput(Input):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class PositionInput(Input):
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)


class GraphNodeInput(Input):
    id: UUID
    type: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)
    alias: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    position: PositionInput
    config: dict = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def credentials_are_references(cls, config):
        connection_references(config)
        return config


class GraphEdgeInput(Input):
    id: UUID
    source: UUID
    target: UUID
    sourceHandle: str | None = Field(default=None, max_length=30)
    targetHandle: str | None = Field(default=None, max_length=30)


class DefinitionInput(Input):
    schema_version: int = 1
    nodes: list[GraphNodeInput] = Field(default_factory=list, max_length=200)
    edges: list[GraphEdgeInput] = Field(default_factory=list, max_length=400)


class WorkflowInput(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    definition: DefinitionInput = Field(default_factory=DefinitionInput)


class DraftInput(Input):
    expected_revision: int = Field(ge=1)
    definition: DefinitionInput | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class RunInput(Input):
    payload: dict = Field(default_factory=dict)
    test: bool = False
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class ConnectionInput(Input):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["bearer", "api_key", "basic", "postgres"]
    secret: dict
    allow_writes: bool = False
    allowed_hosts: list[str] = Field(default_factory=list, max_length=20)


class ConnectionPatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    secret: dict | None = None
    enabled: bool | None = None
    allow_writes: bool | None = None
    allowed_hosts: list[str] | None = Field(default=None, max_length=20)


class ScheduleInput(Input):
    workflow_id: str
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(min_length=1, max_length=120)
    enabled: bool = True


class SchedulePreview(Input):
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(min_length=1, max_length=120)


class EnabledInput(Input):
    enabled: bool


class KeyInput(Input):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[Literal["workflows:read", "runs:read", "runs:write"]]
    expires_days: int = Field(default=90, ge=1, le=365)


class MemberInput(Input):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "editor", "viewer"]


class RoleInput(Input):
    role: Literal["admin", "editor", "viewer"]


class WorkspaceInput(Input):
    name: str = Field(min_length=1, max_length=120)
    environment: Literal["development", "staging", "production"]


class SettingsInput(Input):
    name: str = Field(min_length=1, max_length=120)
    retention_days: int = Field(ge=1, le=3650)


class HookInput(Input):
    hmac_secret: str | None = Field(default=None, min_length=20, max_length=500)
