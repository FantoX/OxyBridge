import ssl
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from oxybridge.api import send_reset
from oxybridge.config import Settings


def configured(**values):
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgres_urls_work_without_provider_specific_configuration(scheme):
    value = configured(
        database_url=f"{scheme}://user:p%40ss@db.example.com/app?sslmode=verify-full"
    )
    assert (
        value.database_url
        == "postgresql+psycopg://user:p%40ss@db.example.com/app?sslmode=verify-full"
    )


def test_database_configuration_is_required_and_environment_wins(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError):
        configured()
    config = tmp_path / ".env"
    config.write_text("DATABASE_URL=postgresql://file:private@file.example.com/file\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://env:private@env.example.com/env")
    assert Settings(_env_file=config).database_url.endswith("@env.example.com/env")


@pytest.mark.parametrize("url", ["sqlite:///app.db", "mysql://u:p@db/app", "not a URL"])
def test_unsupported_database_urls_fail_without_exposing_passwords(url):
    with pytest.raises(ValidationError) as error:
        configured(database_url=url)
    assert url not in str(error.value)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_hosted_environments_require_secure_explicit_origins(environment):
    values = dict(
        app_env=environment,
        app_base_url="https://workflow.example.com/",
        session_cookie_secure=True,
        cors_allowed_origins=["https://workflow.example.com"],
    )
    assert configured(**values).app_base_url == "https://workflow.example.com"
    for origin in (
        "*",
        "https://*.example.com",
        "http://localhost:5174",
        "https://app.example.com/path",
    ):
        with pytest.raises(ValidationError):
            configured(**{**values, "cors_allowed_origins": [origin]})
    with pytest.raises(ValidationError):
        configured(**{**values, "session_cookie_secure": False})
    with pytest.raises(ValidationError):
        configured(**{**values, "app_env": "prodution"})


def test_rejected_requests_keep_security_headers(client):
    for raw, status in ((b"{", 400), (b"x" * 1_048_577, 413)):
        response = client.post(
            "/api/v1/auth/login", content=raw, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == status
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-request-id"]


def test_password_reset_smtp_validates_the_certificate():
    server = MagicMock()
    with patch("oxybridge.api.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        send_reset("recipient@example.com", "reset-token")
    context = server.starttls.call_args.kwargs["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
