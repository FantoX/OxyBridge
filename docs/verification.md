# Compatibility and verification

OxyBridge is a lightweight workflow automation application with a visual editor, durable execution, and environment-based deployment configuration. This reference describes its supported capabilities, validation evidence, and current operating limits.

The application baseline was verified on **October 13, 2026**. Commit-specific checks are linked from each [release](https://github.com/FantoX/OxyBridge/releases).

## Release checks

| Check | Evidence |
| --- | --- |
| GitHub Actions | [Passing validation run](https://github.com/FantoX/OxyBridge/actions/runs/38378227528) for application commit `0c1e76c`: Linux, Python 3.12, Node.js 24, disposable PostgreSQL 18, full backend/frontend/browser checks and dependency scans. |
| Backend | **78 passed**. Graph, expression, state, HTTP/SQL contracts, auth, tenant isolation, CSRF/RBAC, secrets, scheduling, retries, outbox, recovery, idempotency, concurrency, retention, and migration tests. Added configuration/SMTP/header, hostile JSON Schema, and execution-stream connection/thread regressions in this review. |
| Frontend | Five editor state tests; ESLint, strict TypeScript, and production Vite build. |
| Browser compatibility | **24 passed** in Linux CI across Chromium, Firefox, and WebKit. Each includes a real canvas/edit/publish/run/inspect flow, management/theme checks, and all major screens at 320, 360, 390, 768, 1024, and 1440px. Test sessions are reused per worker so the suite respects login throttling. |
| Responsive interactions | Navigation drawer, editor node selection/inspector/palette, publication button geometry, execution detail, and connection dialogs. Tests reject page overflow and uncaught/CSP errors. Screenshots use an isolated local instance and demo records. |
| Built UI compatibility | An additional **24 passed** on Windows against the production frontend served from the rebuilt Linux container. The same three engines and screen widths passed with the real CSP enabled. |
| Portable runtime | Multi-stage image built on Linux; clean local PostgreSQL migrated to 0002; ASGI served the built frontend and API on one origin; repeated migrations passed. App/database readiness and continuous service startup verified. |
| Hosted release | Readiness, authentication, frontend security headers, six concurrent execution snapshots, and two real Chromium edit/publish/run/inspect and management/mobile flows passed after the final application update. |
| Continuous processing | `scripts/check_runtime.py` passed a signed webhook/replay check, a 12-second durable wait resumed without browser advancement, and a minute-level cron run completed through continuous services. Verification schedules were removed and workflows archived afterward. |
| Dependencies | Runtime Python and frontend package scans found no known vulnerabilities at the application review. The publication scan subsequently identified six advisories in the development installer; release `0.1.1` pins the patched installer for development and container builds, and expands CI to audit development requirements. See the [changelog](../CHANGELOG.md#011---2026-10-13). Scans are time-bounded evidence, not a guarantee of future advisories. |
| Security | Source review and regression tests are documented in [SECURITY.md](../SECURITY.md). Private configuration is excluded from Git and container context. |

## Capability reference

**Implemented** identifies available behavior with source, test, or runtime evidence. **Available with limits** and **Limited** identify configuration needs, feature boundaries, or incomplete operational verification. **Planned** features are not available in this release.

| Capability | Status | Behavior and limits |
| --- | --- | --- |
| Email/password, password hashing, refresh/logout | Implemented | Argon2id, rotating opaque cookies, session revocation, profile/password settings, reset tokens and account enumeration protection. |
| Password reset email | Limited | SMTP code and verified STARTTLS context implemented; actual email delivery requires operator service configuration. Admin CLI reset is available. |
| MFA / identity providers | Planned | Not available in the current release. |
| Organizations/workspaces/roles | Available with limits | Organization-aware schema, memberships, multiple workspaces, workspace switcher and server authorization. Self-service organization creation/administration is not provided. |
| Canvas, node/edge editing, zoom, fit | Implemented | React Flow nodes/handles, drag/drop palette, panning/zoom, minimap, multi-select and keyboard/menu actions. |
| Duplicate/copy/paste/undo/redo | Implemented | New stable UUIDs for copied graphs and atomic history operations. |
| Autosave/unsaved edits | Implemented | Debounced optimistic revision saves, conflict recovery, valid local draft recovery, invalid JSON isolation, navigation protection. |
| Validate/test/publish/view versions | Implemented | Validation blocks invalid publication; test snapshots and published definitions are immutable and inspectable. |
| Enable/disable/archive | Implemented | Pause/resume and archive/restore workflows with audited actions. |
| Manual/API/webhook triggers | Implemented | Authenticated API/manual run, random webhook token, optional timestamped HMAC, body/content restrictions, replay deduplication. |
| Schedule trigger / Scheduler | Implemented | Five-field cron, timezone, next-five preview, last/next timestamps, enable/disable; real continuous scheduler run verified. Missed occurrences coalesce. |
| JSON validation | Supported with bounds | Self-contained draft 2020-12, valid/invalid branches, bounded regex/error handling. Remote references, nested draft switches, and patterns combined with unevaluated-properties are rejected. |
| Transform, variable, conditions | Implemented | Type-preserving dot-path mappings, variables, AND/OR groups, comparisons, contains/exists and bounded regex. |
| Delay | Implemented | Durable scheduled node state; a waiting node does not retain an idle worker. |
| HTTP actions | Implemented | Methods, URL/body/query/header mapping, timeout, expected status, response extraction, bearer/API-key/basic connections, bounded redirects/responses. |
| PostgreSQL action | Implemented | Prepared parameters, read-only default, explicit writes, TLS modes, statement timeout and result limits; real PostgreSQL contract tests. |
| Callback | Implemented | POST HTTP callback with the same outbound protections. |
| Later connectors / OAuth | Planned | Additional connectors and OAuth lifecycle support are planned. |
| Expressions/context | Implemented | Restricted trigger/node/variable/environment/run paths; no process-environment or arbitrary-code access. |
| Validation | Available with limits | Topology, handles, UUIDs, sizes, schemas, credential scopes, supported expressions and static upstream references. Full inferred input/output type compatibility is not implemented. |
| Execution/orchestration | Implemented | Persisted run/node/attempt state, branch/merge rules, ready-node orchestration and terminal-state computation. |
| Idempotency/delivery | Implemented | Request hash/key checks and tested duplicate delivery; external effects remain at least once. |
| Transactional outbox | Implemented | Atomic run/event persistence, leased row claims, expiry/recovery, retries and contention tests. |
| Durable delivery runtime | Runtime design | PostgreSQL outbox and continuous dispatcher provide durable event delivery. |
| Retries | Implemented | Per-node maximum attempts, capped exponential backoff, jitter, retryable error classification and visible attempt history. |
| Failed work/recovery | Available with limits | Dead-letter history, acknowledgment, safe linked whole-run recovery. Retrying an individual failed node is not exposed. |
| Cancellation | Implemented | Queued/running cancellation stops later work. Already-started external effects may finish. |
| Schema/API boundaries | Implemented | Models and frozen migrations, pinned versions, scoped REST resources, strict request schemas and stable error contracts. |
| Live UI/state | Implemented | SSE snapshots with polling fallback and separate server/editor state. |
| Application screens | Implemented | Login, overview, workflows, builder, history/detail, connections, schedules, failed work, templates, audit and settings. |
| Advanced list filters | Limited | Name/status workflow search and workflow/status/trigger/date/run-ID history filters exist. Owner/trigger/recent-failure workflow filters and duration-range history filters are not exposed. |
| Inspector test-node action | Limited | Whole-workflow test console exists; isolated arbitrary node testing is not exposed. |
| Errors/destructive UX | Implemented | Confirmation dialogs for destructive actions, actionable server errors, invalid-field messages, optimistic-save conflict handling. |
| Accessibility | Available with limits | Labels, focus states, dialogs, keyboard controls, status text/icons, reduced motion and mobile touch checks. No independent WCAG conformance certification. |
| Security | Available with limits | Reviewed protections, fixed SMTP/header/schema issues, SSRF/RBAC/CSRF/redaction/scoping regressions and dependency scans. Independent penetration testing remains outstanding. |
| Logs | Available with limits | Structured JSON event logs and request/run/node identifiers. Not every event emits the same optional metadata fields. |
| Metrics / Dashboard | Limited | API/workflow metrics, persisted activity/latency/health summaries and service heartbeats exist. Full DB-pool, egress, scheduler-lag metric inventory and a prebuilt monitoring dashboard are not provided. |
| Tracing | Limited | OpenTelemetry spans and optional OTLP export exist; collector delivery and complete cross-process trace propagation are not certified. |
| Health | Implemented | Dependency-free process liveness and database readiness with 503 on failure. |
| Docker/Compose | Implemented | Standard non-root image, migration task, API/static UI, dispatcher, scheduler, optional private local database. |
| High availability and autoscaling | Limited | The lightweight runtime can run on a single ASGI host or container. HA/autoscaling policies and production SLOs have not been certified. |
| Graceful shutdown | Limited | Signal handlers stop service dispatch; leases enable recovery. A real interrupted external-effect/failover drill is outstanding. |
| Backup/restore | Available with limits | Guarded backup/restore utility and verified historical restore. Recurring offsite backups and a production cutover require operator configuration and testing. |
| Autosave/versioning/import/export | Implemented | Draft revisions, immutable version hashes/metadata, import/export with connection references and no exported secrets. |
| Limits | Implemented | Node/edge/request/response/output/retry/run bounds; large object-store payloads are deferred. |
| Performance | Limited | Modest concurrency correctness checked. Sustained load, p95/p99 latency, throughput, failover and availability targets are not certified. |
| Tests | Available with limits | Backend contracts/integration/security, editor state, success E2E and browser screens. Full browser-driven transient failure → recovery journey is not yet a dedicated E2E case. |
| CI/release | Available with limits | GitHub Actions pipeline and pinned build/test/audit steps; release/rollback guide. Live production rollback/cutover remains unverified. |
| Audit | Implemented | Security-sensitive account, membership, workflow, connection, key, schedule and recovery changes are persisted without secret bodies. |
| Product documentation | Available with limits | Product README, screenshots, diagram, templates, operational docs and API example. Recorded demo video and sustained benchmark report are not included. |
| Order fulfillment example | Demonstration | Nine-node validation/routing/HTTP/SQL/callback template. Earlier remote echo and real SQL checks passed; real inventory/shipping integrations need user endpoints. |
| Retention | Implemented | Bounded retention, protected unresolved failures and recovery links, payload redaction/removal, auditable workspace setting. |
| Environment configuration | Implemented | Required PostgreSQL URL, generated private keys, environment precedence, strict environment/origin validation, configurable runtime/pooling/limits. |
| Runbooks | Implemented | Deployment, scheduling, failure diagnosis, outages, backup/restore, upgrades/rollback, password/secret rotation, monitoring. |
| SLOs/alerts | Limited | Operational alert recommendations exist; live alert delivery and SLO validation are outstanding. |
| Planned extensions | Planned | OAuth, Slack/email action connectors, bounded loops/batches, object storage, approvals, live collaboration, marketplace, billing and HA are not completed features. |

## Historical evidence

The previous release passed 54 backend tests, five frontend state tests, two hosted browser flows, signed webhook replay, both order-value branches through public HTTPS echo calls, real PostgreSQL writes, invalid-input failure/dead-letter handling, and demo-role isolation from application users.

A custom-format PostgreSQL dump was restored into a fresh local PostgreSQL 18 database at migration 0002. Counts were one user, five workflows, seven versions, two runs, and one connection. The connection decrypted with the instance key; restored work was never dispatched. This was a point-in-time snapshot, so its counts do not describe current state.

Twenty two-node runs processed through five concurrent drains in 5.03 seconds with correct outputs. Four concurrent deliveries of a queued HTTP node produced one external call. These are correctness checks at modest load, not production throughput/SLO benchmarks.

## Operating and validation limits

The workflow core is functional, portable, and tested within the scope recorded above. Sustained production load, real failover/rollback, alert delivery, and independent security verification remain outstanding. Feature availability and operator configuration needs are listed in the capability reference.

Screenshots depict the tested application with isolated demo data. Browser-engine tests are not proof for every physical phone, operating system, browser version, or database provider. An upstream test-client deprecation warning remains development-only and does not fail the suite.
