<p align="center">
  <img src="docs/brand/oxybridge.svg" width="280" alt="OxyBridge" />
</p>

<h3 align="center">Connect systems. Orchestrate work. See every execution.</h3>

<p align="center">
  Visual workflow automation for APIs, webhooks, PostgreSQL, and scheduled work.<br />
  Build a connection, set its rules, and follow every step from event to outcome.
</p>

<p align="center">
  <a href="https://github.com/FantoX/OxyBridge/actions/workflows/ci.yml"><img src="https://github.com/FantoX/OxyBridge/actions/workflows/ci.yml/badge.svg" alt="Validation pipeline" /></a>
  <img src="https://img.shields.io/badge/version-0.1.0-6355df" alt="Version 0.1.0" />
  <img src="https://img.shields.io/badge/Python-3.12-3776ab" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/React-TypeScript-167789" alt="React and TypeScript" />
</p>

<p align="center">
  <a href="#what-you-can-build">Features</a> ·
  <a href="#get-started">Get started</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/operations.md">Deployment</a> ·
  <a href="docs/verification.md">Verification</a>
</p>

![OxyBridge dashboard showing workflow activity, health, and recent executions](docs/screenshots/dashboard.png)

## What you can build

An order arrives through a webhook. OxyBridge validates its payload, selects a branch, maps the fields, calls an API, writes a result, and sends a callback. If a dependency fails, the retry and its outcome stay visible in the same execution history.

| Build visually                                                                           | Run reliably                                                                        | Work securely                                                                                 |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Drag nodes onto a pannable canvas; connect branches and merges.                          | Publish immutable versions and keep each execution tied to its original definition. | Sign in with Argon2id passwords, rotating HttpOnly sessions, and CSRF protection.             |
| Configure JSON schemas, conditions, mappings, variables, delays, HTTP requests, and SQL. | Use bounded retries, backoff, idempotency keys, cancellation, and durable recovery. | Encrypt connection credentials and runtime payloads with AES-GCM; redact inspectable results. |
| Undo, redo, duplicate, copy, paste, import, export, and recover unsaved drafts.          | Inspect node inputs, outputs, timings, attempts, errors, and branch decisions.      | Restrict access by workspace, role, API-key scope, and approved integration hostname.         |
| Start from reusable templates or a blank workflow.                                       | Trigger work manually, by API, signed webhook, or timezone-aware schedule.          | Block private-network requests by default; verify TLS and parameterize SQL.                   |

## A workspace for the whole workflow

### Design the flow

The editor brings the node palette, graph, configuration inspector, validation, version history, and test console into one workspace. Autosave uses revision checks to protect against conflicting edits. Invalid JSON stays visible for correction and blocks publication.

![Visual workflow editor with a condition inspector and connected branches](docs/screenshots/builder.png)

### Understand the outcome

Follow live status, open a node's attempt history, and inspect redacted input and output. Failed work has a dedicated recovery screen, while audit history records security and workspace changes.

![Execution detail with a node timeline and inspectable output](docs/screenshots/execution.png)

### Take the workspace with you

Light and dark themes, a mobile navigation drawer, responsive lists and forms, and a touch-accessible editor support daily work across screen sizes. The canvas pans and zooms so larger graphs remain navigable on a phone.

<table>
  <tr>
    <td width="72%"><img src="docs/screenshots/dashboard-dark.png" alt="OxyBridge dashboard in dark mode" /></td>
    <td width="28%"><img src="docs/screenshots/mobile.png" alt="OxyBridge dashboard on a phone" /></td>
  </tr>
</table>

## Own your deployment

OxyBridge runs as a standard **ASGI application** or **Docker container**, with a static React frontend and a **PostgreSQL database**. Choose your own hosting and PostgreSQL provider. Database credentials, instance keys, URLs, email settings, and runtime limits come from environment variables.

```mermaid
flowchart LR
  UI[Visual workspace] --> API[FastAPI]
  Events[API / webhook] --> API
  API --> DB[(PostgreSQL)]
  DB --> Worker[Durable dispatcher]
  Scheduler[Scheduler] --> DB
  Worker --> Integrations[HTTP / PostgreSQL / callbacks]
  Worker --> DB
  DB --> API
```

The database stores workflow definitions, execution history, and a transactional outbox. An always-on dispatcher and scheduler provide unattended processing. On a host with short-lived processes, use the authenticated scheduler tick and allow sufficient invocation time. Pending work persists until a processor resumes it.

**Database compatibility:** the current engine requires PostgreSQL and is tested on PostgreSQL 18. Any provider offering compatible PostgreSQL can be configured through `DATABASE_URL`; other database engines are not supported as the application store.

## Get started

Clone the repository:

```sh
git clone https://github.com/FantoX/OxyBridge.git
cd OxyBridge
```

### Run the complete stack locally

You need Docker with Compose and Python 3.12 to generate the private configuration. Node.js and application dependencies are installed inside the image.

```sh
python -m oxybridge.cli init-config
```

This creates `.env` with unique instance keys and refuses to overwrite an existing file. Set `POSTGRES_PASSWORD` in that file to a new URL-safe password, then start the app, local database, dispatcher, and scheduler:

```sh
docker compose -f compose.yaml -f compose.local.yaml up --build -d
```

Open **http://localhost:8000**. The first-run screen creates the owner account using your private `SETUP_TOKEN` from `.env`. Explore Templates to create your first workflow. The local database uses a persistent named volume and is not exposed on a host port.

To use an existing PostgreSQL database, set `DATABASE_URL` in `.env` and run `docker compose up --build -d` with the base file. Configure `APP_BASE_URL` and `CORS_ALLOWED_ORIGINS` for the URL you open. See [configuration](docs/configuration.md) and [production operations](docs/operations.md).

### Develop with Python and Node.js

Use Python 3.12, Node.js 24, and a separate development PostgreSQL database. These PowerShell commands use the pinned dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci --prefix web
.\.venv\Scripts\python.exe -m oxybridge.cli init-config
```

Set `DATABASE_URL` in `.env`, then run:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m oxybridge.cli seed --email owner@example.com
.\.venv\Scripts\python.exe -m uvicorn oxybridge.api:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```powershell
npm run dev --prefix web
```

Open **http://localhost:5174**. The development seed writes the generated password to ignored `.local/login.json`; it never changes an existing instance. Production uses the protected setup screen instead. Run the dispatcher and scheduler in additional terminals for unattended schedules and delayed retries:

```sh
python -m oxybridge.services dispatcher
python -m oxybridge.services scheduler
```

On macOS/Linux, use `python3.12 -m venv .venv` and `.venv/bin/` in place of the Windows executable paths. To serve the production frontend from the API, run `npm run build --prefix web` before starting the ASGI process.

## Integrate through the API

Create a scoped API key in Settings, publish a workflow, and invoke it from another system:

```sh
curl -X POST "$APP_BASE_URL/api/v1/workflows/$WORKFLOW_ID/run" \
  -H "Authorization: Bearer $OXYBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-2041" \
  -d '{"payload":{"order_id":"ORD-2041","total":749}}'
```

The API returns `202` with a `run_id` and persisted status. Reusing a key with the same input returns the original run; different input returns `409`. Inspect the result at `/api/v1/workflow-runs/{run_id}`. Interactive API documentation is available at `/docs` on your instance.

The Order Fulfillment template includes HTTP, database storage, and callback steps. Configure your own encrypted connection and endpoints before publishing. Test runs execute real actions, so use isolated integrations and idempotent writes.

## Security and verification

The review covers authentication, CSRF/CORS, tenant isolation, roles and API scopes, encrypted credentials, secret redaction, webhook replay, outbound requests, SQL, security headers, dependency scans, and container permissions. See [the security review](SECURITY.md) and [requirement-by-requirement verification](docs/verification.md) for evidence and limits.

**Verified October 13, 2026:** 78 backend tests, 5 frontend state tests, and 24 browser checks across Chromium, Firefox, and WebKit passed in the [validation pipeline](https://github.com/FantoX/OxyBridge/actions/runs/38378227528), alongside lint, production builds, and dependency scans. Responsive checks cover widths from 320px to 1440px.

Tests use a disposable database ending in `_test`. They recreate application tables and must never target an instance containing business data.

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres:YOUR_TEST_PASSWORD@127.0.0.1:5432/oxybridge_test'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check oxybridge tests scripts
npm run lint --prefix web
npm test --prefix web
npm run build --prefix web
```

Browser tests require an isolated running app and private `E2E_EMAIL` / `E2E_PASSWORD` configuration. Install test browsers with `npx playwright install chromium firefox webkit` from `web/`, then run `npm run e2e --prefix web`. Set `E2E_BASE_URL` for a different instance. CI uses a disposable PostgreSQL service and runs the same checks.

## Release scope

This release delivers the lightweight workflow core. The [original roadmap](OxyBridge_Production_Development_Roadmap.md) contains broader production and future-release targets; [the verification matrix](docs/verification.md) separates delivered behavior, architectural adaptations, and remaining work.

External effects use **at-least-once delivery**. An interruption after an external action can repeat it: use downstream idempotency support, unique business keys, and SQL UPSERT. SMTP and telemetry export need your service configuration. Sustained production SLOs, independent penetration testing, OAuth/SSO, collaborative editing, and advanced connectors are not claimed for this release.

## Explore the project

| Area                                                    | Location                                                                                       |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| API, authentication, nodes, execution, durable services | [`oxybridge/`](oxybridge/)                                                                     |
| Visual workspace and editor state                       | [`web/src/`](web/src/)                                                                         |
| Database migrations                                     | [`migrations/`](migrations/)                                                                   |
| Portable runtime                                        | [`Dockerfile`](Dockerfile), [`compose.yaml`](compose.yaml)                                     |
| Configuration reference                                 | [`docs/configuration.md`](docs/configuration.md)                                               |
| Deployment, backups, recovery, upgrades                 | [`docs/operations.md`](docs/operations.md)                                                     |
| Design decisions and execution semantics                | [`docs/architecture.md`](docs/architecture.md)                                                 |
| Tests and release evidence                              | [`tests/`](tests/), [`web/tests/`](web/tests/), [`docs/verification.md`](docs/verification.md) |

<p align="center">Build by FantoX · Built for connections you can understand.</p>
