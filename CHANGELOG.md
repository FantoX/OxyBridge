# Changelog

Changes are recorded by released application version. Git tags use `vMAJOR.MINOR.PATCH`; see [release policy](docs/releases.md).

## [Unreleased]

No unreleased changes are currently listed.

## [0.1.2] - 2026-10-14

### Documentation

- Make the capability and compatibility reference self-contained, with clear feature availability, validation evidence, and operating limits.
- Refresh product, architecture, and release guidance with consistent navigation and versioned setup examples.
- Package the release with current user and contributor documentation.

### Upgrade

This is a documentation and release-metadata update. It adds no database migrations, workflow format changes, or dependency changes. Preserve instance configuration and encryption keys when deploying the tagged source or rebuilding the container.

## [0.1.1] - 2026-10-13

### Security

- Upgrade the pinned development installer and the container installer to `pip 26.2.1`. This resolves six published installer advisories: [GHSA-qwm4-qh6w-59xr](https://github.com/advisories/GHSA-qwm4-qh6w-59xr), [GHSA-wf93-45jw-7689](https://github.com/advisories/GHSA-wf93-45jw-7689), [GHSA-jp4c-xjxw-mgf9](https://github.com/advisories/GHSA-jp4c-xjxw-mgf9), [GHSA-58qw-9mgm-455v](https://github.com/advisories/GHSA-58qw-9mgm-455v), [GHSA-6vgw-5pg2-w6jp](https://github.com/advisories/GHSA-6vgw-5pg2-w6jp), and [GHSA-4xh5-x5gv-qwph](https://github.com/advisories/GHSA-4xh5-x5gv-qwph).
- Extend CI's Python vulnerability scan to the complete development requirements, which also include the runtime requirements.

### Distribution

- Include the application license and attribution notices in the portable container, alongside the existing frontend dependency notices.

### Upgrade

Reinstall `requirements-dev.txt` for local development, or rebuild the container from this tag. Preserve the instance environment and encryption keys. This patch has no database migrations, workflow format changes, or runtime dependency changes.

## [0.1.0] - 2026-10-13

Initial public release of the lightweight workflow automation core.

### Added

- Visual workflow editor with connected branches, node configuration, autosave, revision conflict handling, undo/redo, import/export, and immutable published versions.
- Manual, API, signed webhook, and timezone-aware schedule triggers; validation, mapping, variables, conditions, delay, HTTP, PostgreSQL, and callback nodes.
- Durable execution state, transactional outbox, bounded retries, cancellation, recovery, attempt history, and redacted live inspection.
- Workspace roles, scoped API keys, encrypted credentials and payloads, audit history, and retention controls.
- Light/dark themes and responsive layouts verified from 320px to 1440px across Chromium, Firefox, and WebKit.
- Portable ASGI and non-root Docker deployment, optional local PostgreSQL, continuous dispatcher/scheduler, configuration reference, and operations runbooks.
- Product README, real application screenshots, API example, security review, and capability verification reference.
- Apache 2.0 license, third-party notices, contributor guidance, issue templates, and release/version consistency checks.

### Fixed

- Certificate verification for SMTP STARTTLS and consistent security headers on request rejections.
- Bounded hostile JSON Schema validation and rejection of embedded HTTP authentication values.
- Explicit deployment origins, required environment-based database configuration, and production HTTPS/session validation.
- Mobile inspector selection, accessible compact controls, and tablet execution-detail overflow.
- Execution streams release connections before yielding and read snapshots off the API event loop.
- Hosting project routing and runtime settings are preserved across repository deployments.

### Verification and limits

The application baseline passed 78 backend tests, 5 frontend state tests, and 24 browser checks in Linux CI. Another 24 browser checks passed against the production UI served by the Linux container, and two hosted browser flows passed after deployment repair. See [verification](docs/verification.md) for evidence and operating limits.

This is a source release of an early `0.x` application. External actions are delivered at least once. Sustained production SLOs, independent penetration testing, HA failover, and production compatibility certification remain outstanding.

[Unreleased]: https://github.com/FantoX/OxyBridge/compare/v0.1.2...main
[0.1.2]: https://github.com/FantoX/OxyBridge/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/FantoX/OxyBridge/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/FantoX/OxyBridge/releases/tag/v0.1.0
