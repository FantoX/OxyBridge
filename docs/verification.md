# Verification and requirement status

Review date: **October 13, 2026**. The supplied roadmap is a build specification with MVP, infrastructure, production V1, and later-release targets. This matrix records delivered behavior without treating future goals or unverified SLOs as completed features.

## Release checks

| Check | Evidence |
| --- | --- |
| Backend | **77 passed**. Graph, expression, state, HTTP/SQL contracts, auth, tenant isolation, CSRF/RBAC, secrets, scheduling, retries, outbox, recovery, idempotency, concurrency, retention, and migration tests. Added configuration/SMTP/header and hostile JSON Schema regressions in this review. |
| Frontend | Five editor state tests; ESLint, strict TypeScript, and production Vite build. |
| Browser compatibility | **24 passed** across Chromium, Firefox, and WebKit. Each includes a real canvas/edit/publish/run/inspect flow, management/theme checks, and all major screens at 320, 360, 390, 768, 1024, and 1440px. Test sessions are reused per worker so the suite respects login throttling. |
| Responsive interactions | Navigation drawer, editor node selection/inspector/palette, publication button geometry, execution detail, and connection dialogs. Tests reject page overflow and uncaught/CSP errors. Screenshots use an isolated local instance and demo records. |
| Portable runtime | Multi-stage image built on Linux; clean local PostgreSQL migrated to 0002; ASGI served the built frontend and API on one origin; repeated migrations passed. App/database readiness and continuous service startup verified. |
| Continuous processing | `scripts/check_runtime.py` passed a signed webhook/replay check, a 12-second durable wait resumed without browser advancement, and a minute-level cron run completed through continuous services. Verification schedules were removed and workflows archived afterward. |
| Dependencies | Runtime Python and frontend package scans found no known vulnerabilities at review time. This is time-bounded evidence, not a guarantee of future advisories. |
| Security | Source review and regression tests are documented in [SECURITY.md](../SECURITY.md). Private configuration is excluded from Git and container context. |

## Requirement matrix

References are section numbers in [the original specification](../OxyBridge_Production_Development_Roadmap.md). **Delivered** means implemented with source/test/runtime evidence. **Adapted** means the requested lightweight architecture replaces the original infrastructure choice. **Partial** identifies an explicit remaining feature or verification boundary.

| Roadmap requirement | Status | Implementation / remaining work |
| --- | --- | --- |
| §6 Email/password, password hashing, refresh/logout | Delivered | Argon2id, rotating opaque cookies, session revocation, profile/password settings, reset tokens and account enumeration protection. |
| §6 Password reset email | Partial | SMTP code and verified STARTTLS context implemented; actual email delivery requires operator service configuration. Admin CLI reset is available. |
| §6 MFA / identity providers | Future | Marked later in the roadmap; not part of the current core. |
| §7 Organizations/workspaces/roles | Delivered / partial | Organization-aware schema, memberships, multiple workspaces, workspace switcher and server authorization. Self-service organization creation/administration is not provided. |
| §8 Canvas, node/edge editing, zoom, fit | Delivered | React Flow nodes/handles, drag/drop palette, panning/zoom, minimap, multi-select and keyboard/menu actions. |
| §8 Duplicate/copy/paste/undo/redo | Delivered | New stable UUIDs for copied graphs and atomic history operations. |
| §8 Autosave/unsaved edits | Delivered | Debounced optimistic revision saves, conflict recovery, valid local draft recovery, invalid JSON isolation, navigation protection. |
| §8 Validate/test/publish/view versions | Delivered | Validation blocks invalid publication; test snapshots and published definitions are immutable and inspectable. |
| §8 Enable/disable/archive | Delivered | Pause/resume and archive/restore workflows with audited actions. |
| §9 Manual/API/webhook triggers | Delivered | Authenticated API/manual run, random webhook token, optional timestamped HMAC, body/content restrictions, replay deduplication. |
| §9 Schedule trigger / §49,53 Scheduler | Delivered | Five-field cron, timezone, next-five preview, last/next timestamps, enable/disable; real continuous scheduler run verified. Missed occurrences coalesce. |
| §9 JSON validation | Delivered with bounds | Self-contained draft 2020-12, valid/invalid branches, bounded regex/error handling. Remote references, nested draft switches, and patterns combined with unevaluated-properties are rejected. |
| §9 Transform, variable, conditions | Delivered | Type-preserving dot-path mappings, variables, AND/OR groups, comparisons, contains/exists and bounded regex. |
| §9 Delay | Delivered | Durable scheduled node state; a waiting node does not retain an idle worker. |
| §9 HTTP actions | Delivered | Methods, URL/body/query/header mapping, timeout, expected status, response extraction, bearer/API-key/basic connections, bounded redirects/responses. |
| §9 PostgreSQL action | Delivered | Prepared parameters, read-only default, explicit writes, TLS modes, statement timeout and result limits; real PostgreSQL contract tests. |
| §9 Callback | Delivered | POST HTTP callback with the same outbound protections. |
| §9 Later connectors / OAuth | Future | Broader connector library and OAuth lifecycle are later releases. |
| §10 Expressions/context | Delivered | Restricted trigger/node/variable/environment/run paths; no process-environment or arbitrary-code access. |
| §11 Validation | Delivered / partial | Topology, handles, UUIDs, sizes, schemas, credential scopes, supported expressions and static upstream references. Full inferred input/output type compatibility is not implemented. |
| §12 Execution/orchestration | Delivered | Persisted run/node/attempt state, branch/merge rules, ready-node orchestration and terminal-state computation. |
| §13 Idempotency/delivery | Delivered | Request hash/key checks and tested duplicate delivery; external effects remain at least once. |
| §14 Transactional outbox | Delivered | Atomic run/event persistence, leased row claims, expiry/recovery, retries and contention tests. |
| §15 Broker/worker stack | Adapted | PostgreSQL outbox plus continuous dispatcher replace the separate broker/Celery stack. |
| §16 Retries | Delivered | Per-node maximum attempts, capped exponential backoff, jitter, retryable error classification and visible attempt history. |
| §17 Failed work/recovery | Delivered / partial | Dead-letter history, acknowledgment, safe linked whole-run recovery. Retrying an individual failed node is not exposed. |
| §18 Cancellation | Delivered | Queued/running cancellation stops later work. Already-started external effects may finish. |
| §19–25 Schema/API boundaries | Delivered | Models and frozen migrations, pinned versions, scoped REST resources, strict request schemas and stable error contracts. The module layout differs from the suggested folder structure. |
| §26,50 Live UI/state | Delivered | SSE snapshots with polling fallback and separate server/editor state. |
| §30 Required screens | Delivered | Login, overview, workflows, builder, history/detail, connections, schedules, failed work, templates, audit and settings. |
| §30 Advanced list filters | Partial | Name/status workflow search and workflow/status/trigger/date/run-ID history filters exist. Owner/trigger/recent-failure workflow filters and duration-range history filters are not exposed. |
| §30 Inspector test-node action | Partial | Whole-workflow test console exists; isolated arbitrary node testing is not exposed. |
| §31 Errors/destructive UX | Delivered | Confirmation dialogs for destructive actions, actionable server errors, invalid-field messages, optimistic-save conflict handling. |
| §32 Accessibility | Delivered / partial | Labels, focus states, dialogs, keyboard controls, status text/icons, reduced motion and mobile touch checks. No independent WCAG conformance certification. |
| §33–38 Security | Delivered / partial | Reviewed protections, fixed SMTP/header/schema issues, SSRF/RBAC/CSRF/redaction/scoping regressions and dependency scans. Independent penetration testing remains outstanding. |
| §39 Logs | Delivered / partial | Structured JSON event logs and request/run/node identifiers. The exact full field set proposed for every event is not emitted universally. |
| §40 Metrics / §64 Dashboard | Partial | API/workflow metrics, persisted activity/latency/health summaries and service heartbeats exist. Full DB-pool, egress, scheduler-lag metric inventory and a prebuilt monitoring dashboard are not provided. |
| §41 Tracing | Partial | OpenTelemetry spans and optional OTLP export exist; collector delivery and complete cross-process trace propagation are not certified. |
| §42 Health | Delivered | Dependency-free process liveness and database readiness with 503 on failure. |
| §43,44 Docker/Compose | Delivered | Standard non-root image, migration task, API/static UI, dispatcher, scheduler, optional private local database. |
| §45,46 Cluster/HA autoscaling | Adapted / future | No cluster is required for the requested lightweight runtime. HA/autoscaling policies and production SLOs are not claimed. |
| §47 Graceful shutdown | Partial | Signal handlers stop service dispatch; leases enable recovery. A real interrupted external-effect/failover drill is outstanding. |
| §48 Backup/restore | Delivered / partial | Guarded backup/restore utility and verified historical restore. Recurring offsite backups and a production cutover require operator configuration and testing. |
| §51,52 Autosave/versioning/import/export | Delivered | Draft revisions, immutable version hashes/metadata, import/export with connection references and no exported secrets. |
| §54 Limits | Delivered | Node/edge/request/response/output/retry/run bounds; large object-store payloads are deferred. |
| §55,61 Performance | Partial | Modest concurrency correctness checked. Sustained load, p95/p99 latency, throughput, failover and availability targets are not certified. |
| §57–60 Tests | Delivered / partial | Backend contracts/integration/security, editor state, success E2E and browser screens. Full browser-driven transient failure → recovery journey is not yet a dedicated E2E case. |
| §62,63 CI/release | Delivered / partial | GitHub Actions pipeline and pinned build/test/audit steps; release/rollback guide. Live production rollback/cutover remains unverified. |
| §65 Audit | Delivered | Security-sensitive account, membership, workflow, connection, key, schedule and recovery changes are persisted without secret bodies. |
| §79 Portfolio polish | Delivered / partial | Product README, screenshots, diagram, templates, operational docs and API example. Recorded demo video and sustained benchmark report are not included. |
| §81 Flagship fulfillment | Delivered demo | Nine-node validation/routing/HTTP/SQL/callback template. Earlier remote echo and real SQL checks passed; real inventory/shipping integrations need user endpoints. |
| §86 Retention | Delivered | Bounded retention, protected unresolved failures and recovery links, payload redaction/removal, auditable workspace setting. |
| §87 Environment configuration | Delivered | Required PostgreSQL URL, generated private keys, environment precedence, strict environment/origin validation, configurable runtime/pooling/limits. |
| §88 Runbooks | Delivered | Deployment, scheduling, failure diagnosis, outages, backup/restore, upgrades/rollback, password/secret rotation, monitoring. |
| §89 SLOs/alerts | Partial | Operational alert recommendations exist; live alert delivery and SLO validation are outstanding. |
| §91–93 Future roadmap | Future | OAuth, Slack/email action connectors, bounded loops/batches, object storage, approvals, live collaboration, marketplace, billing and HA are not completed features. |

## Historical evidence

The previous release passed 54 backend tests, five frontend state tests, two hosted browser flows, signed webhook replay, both order-value branches through public HTTPS echo calls, real PostgreSQL writes, invalid-input failure/dead-letter handling, and demo-role isolation from application users.

A custom-format PostgreSQL dump was restored into a fresh local PostgreSQL 18 database at migration 0002. Counts were one user, five workflows, seven versions, two runs, and one connection. The connection decrypted with the instance key; restored work was never dispatched. This was a point-in-time snapshot, so its counts do not describe current state.

Twenty two-node runs processed through five concurrent drains in 5.03 seconds with correct outputs. Four concurrent deliveries of a queued HTTP node produced one external call. These are correctness checks at modest load, not production throughput/SLO benchmarks.

## Completion boundary

The core workflow app is functional, portable, and tested. The full original production V1 definition of done is **not certified**: its deployment adaptations, feature gaps, service configuration, sustained load, real failover/rollback, alert delivery, and independent security verification remain explicitly recorded above.

Screenshots depict the tested application with isolated demo data. Browser-engine tests are not proof for every physical phone, operating system, browser version, or database provider. An upstream test-client deprecation warning remains development-only and does not fail the suite.
