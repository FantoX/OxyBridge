import base64
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_base_url: str = "http://localhost:5174"
    database_url: str
    database_pool_size: int = Field(default=2, ge=1, le=20)
    database_max_overflow: int = Field(default=1, ge=0, le=20)
    web_dist_dir: str = "web/dist"
    cron_secret: str = ""
    setup_token: str = ""
    execution_budget_seconds: int = Field(default=25, ge=1, le=120)
    secret_key: str = Field(min_length=32)
    encryption_master_key: str
    session_cookie_secure: bool = False
    cors_allowed_origins: list[str] = ["http://localhost:5174", "http://127.0.0.1:5174"]
    outbound_private_hosts: list[str] = []
    outbound_allowed_hosts: list[str] = []
    webhook_max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    http_node_max_response_bytes: int = Field(default=5_242_880, ge=1024, le=10_485_760)
    run_max_seconds: int = Field(default=3600, ge=1, le=86400)
    run_retention_days: int = Field(default=90, ge=1, le=3650)
    payload_retention_days: int = Field(default=30, ge=1, le=3650)
    audit_retention_days: int = Field(default=365, ge=1, le=3650)
    otel_exporter_otlp_endpoint: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "oxybridge@localhost"
    smtp_starttls: bool = True

    @field_validator("database_url")
    @classmethod
    def postgres_url(cls, value):
        try:
            url = make_url(value)
            if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
                raise ValueError()
            if not url.host or not url.database:
                raise ValueError()
        except Exception as error:
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL with host and database"
            ) from error
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)

    @model_validator(mode="after")
    def production(self):
        try:
            if len(base64.urlsafe_b64decode(self.encryption_master_key)) != 32:
                raise ValueError()
        except Exception as error:
            raise ValueError(
                "ENCRYPTION_MASTER_KEY must be a base64-encoded 32-byte key"
            ) from error
        base = urlsplit(self.app_base_url)
        if (
            base.scheme not in {"http", "https"}
            or not base.netloc
            or base.username
            or base.password
        ):
            raise ValueError("APP_BASE_URL must be an HTTP(S) URL without embedded credentials")
        if base.query or base.fragment or base.path not in {"", "/"}:
            raise ValueError("APP_BASE_URL must be an origin without a path, query or fragment")
        self.app_base_url = self.app_base_url.rstrip("/")
        if self.app_env in {"staging", "production"}:
            if not self.session_cookie_secure or not self.app_base_url.startswith("https://"):
                raise ValueError("Production requires HTTPS and Secure cookies")
            for origin in self.cors_allowed_origins:
                parts = urlsplit(origin)
                if (
                    parts.scheme != "https"
                    or not parts.netloc
                    or parts.path
                    or parts.query
                    or parts.fragment
                    or parts.username
                    or "*" in origin
                ):
                    raise ValueError("Production requires explicit HTTPS CORS origins")
            if len(self.cron_secret) < 32 or len(self.setup_token) < 32:
                raise ValueError("Production requires strong CRON_SECRET and SETUP_TOKEN")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
