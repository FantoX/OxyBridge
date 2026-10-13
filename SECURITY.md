# Security

OxyBridge stores integration credentials, accepts webhook traffic, performs outbound requests, and executes parameterized database operations. Review deployment permissions and integration scopes before exposing an instance.

## Reviewed boundaries

| Boundary | Protection and verification |
| --- | --- |
| Password/session authentication | Argon2id, opaque hashed sessions, rotating refresh tokens, HttpOnly cookies, expiry, logout and revocation checks. |
| Browser mutations | CSRF token and explicit Origin validation. Staging/production require Secure cookies and HTTPS origins. |
| Authorization | API-enforced owner/admin/editor/viewer roles, tenant/workspace isolation, scoped expiring API keys, creator access rechecked on use. |
| Secrets | AES-GCM encryption for credentials/runtime bodies, hashed bearer keys, redacted output/log views; secrets are excluded from response schemas and the published source. |
| Webhooks | Random token, optional timestamped HMAC, replay idempotency, endpoint rate limits, JSON content-type and request body limits. |
| Outbound HTTP | Public unicast IP checks, all-address DNS validation, pinning, verified TLS, bounded redirects/response sizes/timeouts, exact credential hosts, cross-origin credential stripping. |
| SQL | Dedicated encrypted connection, prepared parameters, read-only default, explicit write permission, one query, statement timeout and bounded results. |
| API errors | Redacted error contracts and request IDs. Malformed/oversized request errors retain security headers and no-store caching. |
| Browser content | CSP for served frontend/data routes, frame denial, nosniff, referrer and permissions policies; HSTS for secure-cookie deployments. Interactive API docs have a distinct policy because their UI loads external assets. |
| Container | UID 10001, read-only application filesystem, dropped capabilities, no privilege escalation, no embedded configuration or private files, loopback host binding. |
| Dependencies | Pinned runtime/frontend dependencies and vulnerability scans in CI. Update pinned requirements and lockfiles together, then rerun the checks. |

## Fixes from the October 13, 2026 review

- SMTP STARTTLS now uses a certificate-verifying SSL context. A regression test checks required verification and hostname validation.
- JSON Schema regex checks are bounded, error collection is capped, and unique-item checks use linear hashing. Nested draft switches and an unsafe pattern/unevaluated-properties combination are rejected before publication.
- Request rejections now retain the same security headers and request IDs as normal API responses.
- Hosting-specific automatic CORS trust was removed; configured explicit origins are required.
- Draft/save validation also rejects inline authentication in URL queries, query objects, and HTTP bodies. Runtime expressions remain available for encrypted per-run input; fixed credentials belong in encrypted Connections.
- Database configuration is required, accepted PostgreSQL URLs normalize to the installed driver, and configuration errors hide input values.
- Invalid environment names fail startup; staging applies the same HTTPS/cookie protections as production.
- The portable image and Compose files apply non-root and runtime filesystem/capability restrictions.
- Small-screen editor/search controls retain accessible names when their visible text is hidden.

## Operator responsibilities

Use separate environments and keys; restrict the database/network; terminate HTTPS securely; trust only your actual proxy addresses; require certificate-verified remote database TLS; keep outbound private-host exceptions narrow. Never grant workflow connections access to application user/session tables. Test workflows can perform real effects.

Preserve encryption keys separately from backups. Use short, appropriate payload retention and send only necessary sensitive data. Generic redaction does not recognize every business-sensitive field. At-least-once processing needs downstream idempotency for repeat-safe external effects.

SMTP, telemetry, alerting, and recurring backups need your service configuration. The review is source, automated-test, and runtime verification; it is not an independent penetration test or a claim of zero vulnerabilities. Sustained production load, every database provider, every physical device/browser version, and HA failover have not been certified.

## Report an issue

Report security issues privately to the repository owner using private security advisories where available. Do not publish credentials, personal payloads, executable exploit details, or instance configuration in a public issue. Include the affected version, boundary, and a minimal redacted reproduction.
