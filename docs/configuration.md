# Configuration

All instance configuration is read by `oxybridge.config.Settings`. Environment variables override `.env`. The browser uses same-origin API paths and receives no database credentials or instance keys. `python -m oxybridge.cli init-config` generates unique keys without overwriting existing configuration.

## Required instance values

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Application PostgreSQL URL. Required; no usable credential default is shipped. `postgres://`, `postgresql://`, and `postgresql+psycopg://` are accepted. |
| `SECRET_KEY` | Private secret with at least 32 characters for token digests. Preserve it across restarts. |
| `ENCRYPTION_MASTER_KEY` | URL-safe base64 of 32 random bytes. Existing credentials and runtime bodies depend on this key. |
| `CRON_SECRET` | Bearer secret for scheduler ticks and production metrics; at least 32 characters in staging/production. |
| `SETUP_TOKEN` | Protects initial owner creation; at least 32 characters in staging/production. Setup closes after the first account exists. |

A connection URL has this shape, with credentials supplied privately:

```text
postgresql://USER:URL_ENCODED_PASSWORD@HOST:5432/DATABASE?sslmode=verify-full
```

Use certificate-verified TLS for remote production databases and configure the appropriate PostgreSQL trust root through `sslrootcert` in the URL or libpq environment. A provider requiring a custom CA can use its own CA file. Local container PostgreSQL communicates on the private Compose network; it is intended for local development. URL-encode special characters in usernames/passwords.

## Runtime values

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, `staging`, or `production`. Misspellings fail startup. |
| `APP_BASE_URL` | `http://localhost:5174` | Public origin used in generated webhook/reset URLs. No path, query, fragment, or embedded credentials. |
| `SESSION_COOKIE_SECURE` | `false` | Must be `true` in staging/production; serve the app over HTTPS. |
| `CORS_ALLOWED_ORIGINS` | Local development origins | JSON array of exact origins. Staging/production require HTTPS origins without wildcards. Include the app origin for CSRF checks, even with same-origin hosting. |
| `DATABASE_POOL_SIZE` | `2` | Persistent connections per process, 1–20. Size against the total number of processes and the database connection limit. |
| `DATABASE_MAX_OVERFLOW` | `1` | Additional temporary connections per process, 0–20. |
| `WEB_DIST_DIR` | `web/dist` | Built frontend location. If absent, only the API is served. Restart after building to register static routes. |
| `EXECUTION_BUDGET_SECONDS` | `25` | Request/tick drain budget, 1–120 seconds. A started node may run to its own timeout. |
| `RUN_MAX_SECONDS` | `3600` | Run deadline, 1–86400 seconds. Recovery/orchestration enforces it when processing resumes. |
| `WEBHOOK_MAX_BODY_BYTES` | `1048576` | Request body limit, including API mutations. |
| `HTTP_NODE_MAX_RESPONSE_BYTES` | `5242880` | Accepted outbound HTTP response limit. Stored output has a separate 512 KB engine limit. |
| `OUTBOUND_ALLOWED_HOSTS` | `[]` | JSON array of exact outbound hostnames. Empty permits public hosts subject to SSRF checks. |
| `OUTBOUND_PRIVATE_HOSTS` | `[]` | Explicit administrator-approved private hosts. Keep empty unless an integration requires internal access. |
| `RUN_RETENTION_DAYS` | `90` | Default retention for new workspaces; existing workspaces have their own setting. |
| `PAYLOAD_RETENTION_DAYS` | `30` | Successful/cancelled payload retention. |
| `AUDIT_RETENTION_DAYS` | `365` | Audit retention. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Empty | Optional HTTP OTLP collector base URL. No telemetry exporter is enabled without configuration. |

## Email

Set `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and `SMTP_STARTTLS` (default true). STARTTLS verifies the server certificate. Without email configuration, administrators can use the local password-reset command. Public responses do not reveal whether an account exists.

## Container and operator values

| Variable | Meaning |
| --- | --- |
| `PORT` | Container ASGI listener port; default 8000. Compose fixes the internal port to 8000. |
| `APP_PORT` | Host port for Compose; default 8000. |
| `POSTGRES_PASSWORD` | Required by the optional local-database override. Use a unique URL-safe value; there is no shared default. |
| `OXYBRIDGE_ENV_FILE` | Alternate Compose environment file; default `.env`. This enables isolated test/staging configuration. |
| `FORWARDED_ALLOW_IPS` | Trusted proxy address(es); default `127.0.0.1`. Restrict to your actual reverse proxy; do not blindly trust forwarded headers. |
| `PG_BIN` | Optional directory containing PostgreSQL client tools for backup/restore. Otherwise PATH is used. |
| `RESTORE_DATABASE_URL` | Fresh local database ending in `_test` for guarded restore verification. |
| `OXYBRIDGE_SEED_PASSWORD` | Optional private development seed password; otherwise one is generated. Seed is disabled in staging/production. |
| `TEST_DATABASE_URL` | Disposable backend-test database ending in `_test`; tests recreate application tables. |
| `E2E_BASE_URL` | Browser-test app origin; default `http://localhost:5174`. |
| `E2E_EMAIL`, `E2E_PASSWORD` | Private browser-test account. If absent, tests use ignored `.local/login.json`. |

Workflow connector credentials are stored as encrypted connection records, separately from application instance configuration. They are configured by administrators for the selected workspace and never returned after saving.

Validation nodes use self-contained JSON Schema draft 2020-12. Schema references and nested draft switches are rejected. Use `additionalProperties` with `patternProperties`; combining patterns with `unevaluatedProperties` is not supported. Regex checks have a 50 ms budget, validation has a cooperative one-second budget, and at most 20 errors are collected. A complexity limit produces an inspectable `VALIDATION_LIMIT` failure.

Never commit `.env`, private configuration, generated login files, dumps, or credentials. Use different databases and keys for development, preview, CI, and production.
