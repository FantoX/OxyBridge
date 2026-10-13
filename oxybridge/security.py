import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from argon2 import PasswordHasher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from oxybridge.config import settings

passwords = PasswordHasher()
SENSITIVE = re.compile(
    r"authorization|cookie|password|secret|token|api.?key|credential|signature", re.I
)


def connection_references(config):
    headers = config.get("headers", {})
    if isinstance(headers, dict) and any(SENSITIVE.search(key) for key in headers):
        raise ValueError("Authentication headers belong in an encrypted connection")
    if any(config.get(key) for key in ("password", "secret", "token", "api_key")):
        raise ValueError("Credentials belong in an encrypted connection")

    def check(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    SENSITIVE.search(key)
                    and item is not None
                    and not isinstance(item, (dict, list, bool))
                    and str(item)
                ):
                    if not isinstance(item, str) or not re.fullmatch(
                        r"\s*{{\s*(?:trigger|nodes|vars|env|run)(?:\.[A-Za-z0-9_-]+)*\s*}}\s*", item
                    ):
                        raise ValueError(
                            "Inline authentication values are not allowed; use an encrypted connection or a runtime expression"
                        )
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(config.get("query", {}))
    check(config.get("body"))
    if isinstance(config.get("url"), str):
        parts = urlsplit(config["url"])
        if parts.username or parts.password:
            raise ValueError("URLs cannot contain embedded credentials")
        for key, value in parse_qsl(parts.query):
            check({key: value})


def digest(value: str) -> str:
    return hmac.new(settings().secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def content_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def encrypt(value) -> bytes:
    key = base64.urlsafe_b64decode(settings().encryption_master_key)
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, json.dumps(value).encode(), b"oxybridge:v1")


def decrypt(value: bytes):
    key = base64.urlsafe_b64decode(settings().encryption_master_key)
    return json.loads(AESGCM(key).decrypt(value[:12], value[12:], b"oxybridge:v1"))


def secret_values(value):
    if isinstance(value, dict):
        values = [s for v in value.values() for s in secret_values(v)]
        if value.get("username") and value.get("password"):
            values.append(
                base64.b64encode(f"{value['username']}:{value['password']}".encode()).decode()
            )
        return values
    if isinstance(value, list):
        return [s for v in value for s in secret_values(v)]
    return [str(value)] if value is not None and str(value) else []


def sensitive_values(value):
    if isinstance(value, dict):
        return [
            s
            for k, v in value.items()
            for s in (secret_values(v) if SENSITIVE.search(k) else sensitive_values(v))
        ]
    if isinstance(value, list):
        return [s for v in value for s in sensitive_values(v)]
    return []


def redact(value, secrets_to_hide=(), mask_fields=True):
    if isinstance(value, dict):
        return {
            k: "[redacted]"
            if mask_fields and SENSITIVE.search(k)
            else redact(v, secrets_to_hide, mask_fields)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v, secrets_to_hide, mask_fields) for v in value]
    if isinstance(value, str):
        for secret in secrets_to_hide:
            if len(secret) >= 4:
                value = value.replace(secret, "[redacted]")
            elif value in {secret, "Bearer " + secret}:
                value = "[redacted]"
        if value.startswith(("http://", "https://")):
            parts = urlsplit(value)
            query = urlencode(
                [
                    (k, "[redacted]" if mask_fields and SENSITIVE.search(k) else v)
                    for k, v in parse_qsl(parts.query)
                ]
            )
            value = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    return value


def destination(url: str):
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise ValueError("Only HTTP(S) URLs without embedded credentials are allowed")
        host = parts.hostname.lower().rstrip(".")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        policy = settings()
        if policy.outbound_allowed_hosts and host not in policy.outbound_allowed_hosts:
            raise ValueError("Destination is not on the outbound allowlist")
        addresses = sorted(
            {info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )
        if not addresses:
            raise ValueError("Destination did not resolve")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global and host not in policy.outbound_private_hosts:
                raise ValueError("Private, loopback and link-local destinations are blocked")
            if ip.is_multicast or ip.is_unspecified:
                raise ValueError("Destination is not a unicast address")
        return host, addresses[0], port
    except (ValueError, OSError) as error:
        raise ValueError("Destination blocked or unavailable") from error


def limiter(scope: str, limit: int, seconds: int = 60):
    from sqlalchemy.dialects.postgresql import insert

    from oxybridge.db import now, transaction
    from oxybridge.models import RateLimit

    key = digest(f"{scope}:{int(time.time()) // seconds}")
    with transaction() as db:
        statement = insert(RateLimit).values(
            key=key, count=1, expires_at=now() + timedelta(seconds=seconds * 2)
        )
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimit.key], set_={"count": RateLimit.count + 1}
        ).returning(RateLimit.count)
        count = db.scalar(statement)
    if count > limit:
        raise HTTPException(
            429,
            detail={"code": "RATE_LIMITED", "message": "Too many requests. Try again shortly."},
            headers={"Retry-After": str(seconds)},
        )
