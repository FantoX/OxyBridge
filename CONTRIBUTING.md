# Contributing to OxyBridge

Use [Issues](https://github.com/FantoX/OxyBridge/issues) for reproducible bugs and feature proposals. For sensitive security reports, use [private vulnerability reporting](https://github.com/FantoX/OxyBridge/security/advisories/new) and follow [SECURITY.md](SECURITY.md).

## Local development

Fork the repository, clone your fork, and create a focused branch. Follow the [development setup](README.md#develop-with-python-and-nodejs) with Python 3.12, Node.js 24, and your own PostgreSQL database. Generate instance keys locally and keep `.env` and `.local/` private.

Tests recreate application tables. Set `TEST_DATABASE_URL` to a separate disposable database ending in `_test`; never run tests against an instance containing business data. Browser tests execute real workflow actions, so use isolated integrations.

```powershell
python scripts/check_release.py
.\.venv\Scripts\ruff.exe check oxybridge tests scripts
.\.venv\Scripts\python.exe -m pytest
npm run lint --prefix web
npm test --prefix web
npm run build --prefix web
```

Run browser checks against an isolated seeded instance for UI, routing, authentication, and execution changes. Set `E2E_BASE_URL`, `E2E_EMAIL`, and `E2E_PASSWORD`, then run `npm run e2e --prefix web`. CI uses only disposable test configuration.

## Pull requests

Describe the user-visible problem, resulting behavior, and relevant validation. Keep unrelated changes separate. Add a meaningful regression check when changing non-trivial behavior, and update documentation when configuration or supported behavior changes. Record user-visible changes under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).

Do not include private URLs, passwords, tokens, connection strings, personal payloads, local credentials, database dumps, or production logs in issues, commits, screenshots, or test artifacts. Use synthetic examples. Third-party dependency changes must retain their licenses and refresh the frontend notices where needed.

Release versions and tags are maintained through the [release procedure](docs/releases.md). Contributors normally leave version changes to the release preparation commit.

Contributions intentionally submitted for inclusion are offered under Apache 2.0 as described by [LICENSE](LICENSE). Be respectful and keep discussion focused on the work.
