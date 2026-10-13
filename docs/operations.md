# Operations

## Production deployment

Choose an ASGI-capable host or a container runtime and a compatible PostgreSQL instance. The base Compose file uses the database supplied in `DATABASE_URL`; the local override adds a private PostgreSQL service for development.

1. Generate new private instance keys, set the database URL, and preserve the encryption key in a separate secure backup.
2. Set `APP_ENV=production`, `APP_BASE_URL=https://your-domain.example`, `SESSION_COOKIE_SECURE=true`, and explicit `CORS_ALLOWED_ORIGINS` including that origin.
3. Require certificate-verified database TLS and restrict the application database account to the permissions it needs. Use separate integration roles for workflow SQL.
4. Run `alembic upgrade head` as a release task before starting the application. Compose includes a migration service that must finish successfully first.
5. Build `web/dist` and run `uvicorn oxybridge.api:app`, or build and start the provided container. The container honors `PORT`; environment variables contain runtime configuration.
6. Serve production HTTPS through a trusted reverse proxy. Compose binds the app to loopback by default. Restrict trusted forwarded-header sources and ingress access. Apply equivalent security headers if a different server serves the frontend assets.
7. Run `python -m oxybridge.services dispatcher` and `python -m oxybridge.services scheduler` continuously, or configure an authenticated tick with a suitable frequency on a short-lived host.
8. Verify `/health/ready`, create the owner through the protected setup screen, and run an isolated workflow. Configure and verify email/telemetry services if needed.

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 app dispatcher scheduler
```

Configuration is described in [configuration.md](configuration.md). No production secrets are included in the repository. Development and production must use separate databases and keys; copying production configuration into local development makes local edits affect production.

## First sign-in and integrations

On an empty migrated database, use the setup token to create the owner. Afterward, setup returns a conflict and cannot create another owner. Change development seed credentials through Settings before exposing an instance. Add members with the least necessary role.

Use Connections to add and test a credential. Approve the exact HTTP hostname where it may be sent. Use a dedicated PostgreSQL role and leave write permission disabled unless necessary. A connector must never use the application database owner. Test runs execute real actions; begin with isolated endpoints and unique business identifiers.

## Scheduler and delayed work

For unattended processing, the dispatcher drains durable events and recovers abandoned leases; the scheduler creates due runs and applies retention. Multiple instances coordinate through PostgreSQL locks. Keep service clocks synchronized.

Alternatively, invoke `GET /api/v1/system/tick` with `Authorization: Bearer <CRON_SECRET>` from a trusted scheduler. The endpoint rejects missing or wrong secrets. Never put a secret in a URL, frontend bundle, or log. The tick recovers leases, schedules due work, drains a bounded batch, and applies retention.

A live execution view can also call `/advance` with the user's session. Closing that view removes interactive advancement. Pending work remains durable but needs another invocation or dispatcher. Missed cron occurrences coalesce into one run; this is not an exact-time or exactly-once schedule guarantee.

Hosts must allow a running node to complete its timeout and provide graceful process termination time. Termination handlers stop starting new service work; interrupted work resumes after leases expire. Killing a process immediately after an external effect may repeat that effect.

## Diagnose failures

1. Open the execution and inspect its pinned version, node attempts, error code, timings, and redacted results.
2. For scheduled retries, check the next-attempt time and service heartbeat. Do not repeatedly rerun a non-idempotent external action.
3. Fix credentials or the downstream dependency. Recovery uses the original definition and input. Publish a new version and start a new run when the graph must change.
4. Use Failed work to start recovery or acknowledge a resolved failure. The original execution remains inspectable.
5. Cancellation stops later nodes. Reconcile an external request already in progress before replaying it.

If a run is stuck, check readiness, service logs, database connectivity, due outbox events, and expired claims. An authenticated tick can recover expired claims. Preserve records while diagnosing: deleting node state can lose evidence or repeat effects.

## Database outage

Readiness reports 503 when the application database is unavailable. API mutations cannot acknowledge durable work without a committed transaction. Fix connectivity, credentials, certificates, capacity, or the database service, then verify readiness and resume processing. Unsent outbox events remain persisted.

An effect completed just before an outage can be retried. Reconcile using the stable HTTP idempotency key or unique SQL business key. Unit/integration recovery checks do not certify database failover or production outage recovery SLOs.

## Backup and restore

Use PostgreSQL client tools matching the server major version. The utility passes authentication through environment variables, not command-line arguments.

```powershell
.\.venv\Scripts\python.exe scripts/backup.py backup
$env:RESTORE_DATABASE_URL='postgresql://postgres:YOUR_TEST_PASSWORD@127.0.0.1:5432/oxybridge_restore_YYYYMMDD_test'
.\.venv\Scripts\python.exe scripts/backup.py restore-check --dump .local/backups/YOUR_DUMP.dump
```

The restore check rejects remote targets, names without `_test`, and existing databases. It creates a fresh local database, restores definitions/data, checks migration/account/version records, and decrypts credentials with the configured key. It leaves restored records for inspection and never dispatches work.

Only restore trusted dumps: they contain executable database definitions. Back up privately, schedule recurring backups using your infrastructure, enforce retention, and periodically perform restores. The utility does not upload backups or configure a storage provider. A point-in-time restore was verified for the previous release; see [verification](verification.md).

## Upgrade and rollback

1. Back up the database and instance keys; verify a restore into an isolated database.
2. Run CI and test the candidate with staging credentials and controlled integrations.
3. Review schema compatibility and apply migrations. Keep immutable migration history.
4. Deploy the candidate image/build, retain the previous artifact, and verify readiness plus representative success/failure workflows.
5. Roll back application code only when compatible with the current schema. Do not automatically downgrade production data. Test destructive schema changes against a separate restored database before a cutover.

Empty-database and repeated migrations are tested. A real historical production rollback or database cutover has not been certified.

## Passwords and secret rotation

Settings changes the signed-in user's password. Without SMTP, an administrator can run:

```sh
python -m oxybridge.cli reset-password --email owner@example.com
```

The command prompts privately and revokes sessions. Revoke API keys in Settings, rotate webhook tokens in the trigger inspector, and replace integration secrets in Connections. Test before resuming work.

Do not directly replace `ENCRYPTION_MASTER_KEY`: existing ciphertext becomes unreadable. Rotation needs a backed-up decrypt/re-encrypt migration. Rotate `CRON_SECRET` in both the app and external scheduler together. Retain the setup token privately even after setup closes.

## Retention and monitoring

The scheduler applies bounded batches. Defaults are 90 days for run history, 30 for successful/cancelled payloads, and 365 for audit records. Unresolved failures are preserved. Review retention before reducing it; removal is irreversible.

Use `/health/live` for process health and `/health/ready` for database readiness. Production `/metrics` requires the scheduler bearer credential. Metrics are per process and can reset after restarts; dashboard summaries come from persisted records. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to export traces to your collector.

Configure infrastructure alerts for readiness failures, oldest pending outbox age, stale service heartbeats, expired running leases, failed-run increases, connection saturation, and backup failures. Managed email, tracing, and alert delivery require operator configuration and end-to-end verification.
