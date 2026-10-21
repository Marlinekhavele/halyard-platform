# Halyard

The backend of a digital sea freight forwarder for importers in Germany: instant all-in container quotes, online booking, live tracking, document handling, invoicing and an operations API for the team. Built as Python (FastAPI) microservices that talk through events. This repository is backend only. The website and platform app live in a separate repository, [halyard-web](../halyard-web), which generates its API types from this repo's OpenAPI specs (`/api/<service>/openapi.json`). To run them together, start this stack first (`make up`); the frontend stack joins its `halyard` Docker network and gateway.

```
halyard-platform/
├── packages/halyard-common/   shared: config, DB, repository base, errors, JWT auth, events, bus, outbox
│   └── tests/
├── services/
│   ├── accounts/              companies, users, sign-in, tokens
│   ├── commercial/            ports, rates, surcharges, quote engine, bookings, website leads
│   ├── operations/            shipments, containers, milestones, tracking webhook, documents
│   ├── billing/               invoices, partner costs, margin report
│   └── notifications/         emails and in-app alerts, driven only by events
├── scripts/                   dev server (all-in-one), demo seeder, OpenAPI export
├── tests/e2e/                 full quote-to-delivery flow across all services
├── infra/                     Postgres init
├── ruff.toml                  Google Python Style Guide settings
└── docker-compose.yml         gateway, 5 services, Postgres, RabbitMQ, Mailpit, Jaeger
```

## Service layout (repository pattern)

Every service has the same shape: a `src/` package with one folder per layer and one file per entity or feature. Dependencies only point downwards (api/events → services → repositories → models). Commercial as an example:

```
services/commercial/
├── src/commercial/
│   ├── main.py            create_app(settings): wires runtime, consumers, routers
│   ├── core/              config.py, seed.py (+ storage.py / mailer.py / passwords.py
│   │                      in the services that need them)
│   ├── api/               one router per feature: quotes.py, bookings.py, rates.py,
│   │                      leads.py, ports.py; deps.py builds services per request
│   ├── services/          quote_service.py, booking_service.py, rate_service.py,
│   │                      lead_service.py, base.py: business rules, commit decisions
│   ├── repositories/      quote_repository.py, booking_repository.py, ...: all queries
│   ├── models/            quote.py, booking.py, rate.py, ...: SQLAlchemy ORM models
│   ├── schemas/           quotes.py, bookings.py, rates.py, ...: Pydantic API models
│   ├── domain/            pricing.py, reference.py: pure logic with no I/O
│   └── events/            handlers.py: event consumers (operations, billing, notifications)
├── alembic.ini + migrations/   schema migrations for the service's own database
└── tests/
    ├── conftest.py        fixtures: settings, session, service factory, HTTP client
    ├── unit/              services, repositories and domain rules
    └── integration/       HTTP API, event consumers, migrations
```

Each layer package re-exports its public names, so code reads `models.Quote`, `schemas.QuoteOut`, `repositories.QuoteRepository` and `services.QuoteService` regardless of which file a class lives in.

The rules:

- **Routers and consumers stay thin.** `api/` and `events/` never touch the session or the ORM. They call a service method.
- **Services own the business rules.** They raise domain errors from `halyard_common.errors` (`NotFoundError`, `ConflictError`, `PermissionDeniedError`, ...), never `HTTPException`. One exception handler maps them to `{"detail": ...}` with the right status code, so the same service runs behind the API and inside event consumers.
- **Repositories own the queries.** They subclass `halyard_common.repository.Repository[Model]` (`get`, `add`, `add_all`, `count`) and add intention-revealing methods such as `get_by_email` or `find_bookable`. They `flush` but never `commit`.
- **Events go through the outbox.** Services stage events with `OutboxRepository.add(...)` in the same transaction as the change. Event consumers do not commit; `idempotent_consumer` commits once per event.
- **No import-time state.** Each app is built by `create_app(settings)` and keeps its runtime on `app.state`. Request dependencies (`halyard_common.dependencies.Session`, `CurrentUser`, `OpsUser`) read it from there, so every test gets a fresh, isolated app and database.
- **Time and I/O are injectable.** Services take a clock (`today=` / `now=`). Operations takes a `FileStorage` and Notifications takes a `Mailer`, so tests use fakes.

## Code style

The code follows the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html):

- Import modules, not names (`from sqlalchemy import orm` then `orm.Mapped`). Only `typing` and `collections.abc` names are imported directly.
- One import per line, sorted within sections.
- Google-style docstrings (`Args:`, `Returns:`, `Raises:`) on every public module, class and function.
- 80-column lines and 4-space indents.

`ruff.toml` enforces all of this, except module-only imports, which ruff cannot check; keep to it by convention. CI fails on violations:

```bash
make lint      # ruff check + ruff format --check
make format    # apply formatting and safe fixes
```

## Run it

**With Docker (the real microservice setup):**

```bash
cp .env.example .env          # then set JWT_SECRET
make up                       # builds and starts everything, then loads demo data
```

| Open | What |
| --- | --- |
| http://localhost:8080/api/&lt;service&gt;/docs | Interactive API docs per service (accounts, commercial, operations, billing, notifications) |
| http://localhost:8025 | Every email the platform sends (Mailpit) |
| http://localhost:15672 | RabbitMQ (halyard / halyard) |
| http://localhost:16686 | Traces across services (Jaeger) |
| http://localhost:8081 | Gateway dashboard (Traefik) |

Demo sign-ins: **anna@nordwerk.example / demo1234** (importer) and **ops@halyard.example / halyard-ops** (Halyard operations).

**Without Docker (fast local development):** every service runs in one Python process, mounted under `/api/<service>` just like behind the gateway, talking over an in-memory event bus with SQLite files in `.dev/`.

```bash
make install
make dev                      # all APIs on :8080 (make dev PORT=8090 for another port)
make seed                     # in a second terminal: demo shipments (same PORT)
```

**All endpoints in one Swagger UI: http://localhost:8080/docs.** It merges every service's OpenAPI document (`halyard_common.openapi.merge`): paths keep their real `/api/<service>/...` URLs, endpoints are grouped as `service · feature`, and one **Authorize** covers every service because they all accept the same token.

`make openapi` writes each service's OpenAPI spec, plus the combined `halyard.json`, to `docs/openapi/` for client code generation.

## Database migrations

Each service has its own Alembic setup (`services/<service>/alembic.ini` and `migrations/`); the shared environment logic is in `halyard_common.migrations`. Docker containers run `alembic upgrade head` before starting, and compose sets `AUTO_CREATE_TABLES=false`. Local runs and tests keep creating tables on startup for speed.

```bash
make migration svc=billing m="add invoice notes"   # after changing billing models
make migrate                                       # apply every service's migrations
```

`test_<service>_migrations.py` fails when a model changes without a migration. An existing database that was created before migrations existed needs a one-time `alembic stamp head` in each service folder.

## Tests

```bash
make test                     # everything: per-package tests + end-to-end flow (SQLite)
make test-unit                # per-package tests only
make test-e2e                 # end-to-end flow only
make coverage                 # all tests with branch coverage; fails under 90%, report in htmlcov/
E2E_POSTGRES=postgresql+asyncpg://user:pass@localhost:5432 pytest tests/e2e   # same flow on Postgres, plus concurrency tests
```

Coverage settings (sources, branch coverage, the 90% floor) live in `.coveragerc`. `tests/e2e/test_concurrency.py` only runs with `E2E_POSTGRES` set: it fires simultaneous requests to prove that reference numbers stay unique and a quote can only be booked once.

Each package has three kinds of tests:

| Kind | What it covers | How |
| --- | --- | --- |
| Repository | queries, filters, ordering, reference numbers | real SQLite session per test |
| Service | business rules, permissions, state transitions, staged events | service built on a session with a fixed clock and fake I/O |
| API / consumer | routing, auth, status codes, cost hiding, event wiring | `create_app(settings)` + `httpx.ASGITransport`; events published on the in-memory bus |

The end-to-end test signs in, gets a public estimate and a saved quote, books, is refused a double booking and a customer-side confirmation, confirms as ops, waits for the shipment and draft invoice to appear via events, rejects and re-approves a document, posts tracking webhooks (including a bad token), issues the invoice on departure, reports a delay, walks to delivery, marks the invoice paid, checks the margin report, and confirms another company cannot see any of it.

Shared test helpers (`sqlite_url`, `database_session`, `running_client`, `auth_headers`, `customer_user`, `ops_user`) live in `halyard_common.testing`.

## Continuous integration

`.github/workflows/ci.yml` runs on every push to `main` and every pull request:

| Job | What it checks |
| --- | --- |
| Lint | `ruff check` (Google style, docstrings, imports; findings shown inline on the PR) and `ruff format --check` |
| Tests (Python 3.11, 3.12, 3.13) | every test with branch coverage; fails under 90%; HTML and XML reports uploaded as the `backend-coverage` artifact |
| Postgres | end-to-end and concurrency tests on PostgreSQL 16, then for every service: `alembic upgrade head`, `alembic check` (no drift), downgrade and upgrade again |

## Logging

Every service logs through `halyard_common.logs`:

- **Request log:** one line per request with method, path, status and duration (health checks excluded). Unhandled errors are logged with their traceback.
- **Correlation ids:** each request gets an `X-Request-ID` (taken from the gateway if valid, otherwise generated) that is returned in the response and attached to every log line. Events carry it as `correlation_id`, and consumers log under it, so one booking can be followed across Commercial, Operations, Billing and Notifications.
- **Business activity:** every staged event and every handled event (with duration) is logged, as are failed sign-ins (reason and user id only, never the password or the address that was tried).
- **Format:** readable text locally; one JSON object per line with `LOG_JSON=true` (set in docker-compose). `LOG_LEVEL` sets the minimum level.

## How it fits together

```mermaid
flowchart LR
  C[API clients] --> G[Traefik gateway]
  G --> A[accounts] & CO[commercial] & O[operations] & B[billing] & N[notifications]
  A & CO & O & B -- outbox --> MQ[(RabbitMQ)]
  MQ --> O & B & N
  N --> M[SMTP]
  T[Tracking provider] -- webhook --> O
```

- **Each service owns its database** (`halyard_<service>` in Postgres). No service reads another's tables.
- **Services talk through events** on one RabbitMQ topic exchange. There are no synchronous calls between services: Notifications keeps its own copy of users from `accounts.user_created`, Operations gets port names inside `commercial.booking_confirmed`, and so on.
- **Transactional outbox:** a service writes its event into its own `outbox` table in the same transaction as the change; a relay publishes it. Nothing is lost if RabbitMQ is down. **Idempotent inbox:** consumers record processed event ids, so redelivery is harmless. Failed messages go to a dead-letter queue (`<service>.events.dead`).
- **Two-phase startup:** `ServiceRuntime.prepare()` subscribes consumers and `run()` seeds and starts publishing. When services share one process (dev server, e2e test), all of them are prepared before any runs, so startup events such as the seeded demo users reach every subscriber. With RabbitMQ, compose achieves the same by starting consumers first (notifications → billing → operations → commercial, accounts): a queue exists only once its consumer has started.
- **Auth:** Accounts issues JWTs; every service verifies them and enforces company scoping (customers only see their own company's data; ops sees all). Cost prices and margins are never sent to customers.

### The life of a shipment (events)

| Step | Who | Event |
| --- | --- | --- |
| Customer books an option on a quote | Commercial | `commercial.booking_requested` → ops is notified |
| Ops confirms space with the carrier | Commercial | `commercial.booking_confirmed` → Operations opens the shipment (containers, milestones, required documents); Billing drafts the invoice; customer is emailed |
| Customer uploads documents; ops checks them | Operations | `operations.document_uploaded` / `document_reviewed` |
| Tracking provider reports events | Operations | `operations.milestone_reached`, `shipment_delayed`, `customs_hold` |
| Vessel departs | Operations → Billing | invoice issued (`billing.invoice_issued`), customer emailed |
| Containers delivered | Operations | `operations.shipment_delivered` |
| Customer pays | Billing | `billing.invoice_paid` |

## What is real and what is a placeholder

Built and working: all of the above, end to end.

Replace before going live:

| Area | Now | For production |
| --- | --- | --- |
| **Rates** | Seeded planning rates per region pair (`commercial/domain/reference.py`) | Your consolidator and carrier contract rates; edit via `PATCH /rates/{id}` or import |
| **Tracking** | Webhook with a normalised format + ops simulator | An adapter for your provider (e.g. Vizion, Terminal49, Portcast) mapping their payload to `TrackingWebhook` |
| **Carrier booking** | Ops confirms manually via the API | Carrier / NVOCC booking APIs (DCSA standard) when volume justifies it |
| **Container numbers** | Valid ISO 6346 placeholders until the carrier releases real ones | Update from the carrier's booking confirmation |
| **Queue setup outside Docker Compose** | Compose starts consumers first, so their queues exist before anyone publishes | On Kubernetes or similar, declare every queue and binding up front (e.g. a RabbitMQ definitions file) or keep the same start order |
| **Auth** | HS256 shared secret | RS256 with a JWKS endpoint on Accounts, or Keycloak; password reset and email verification |
| **Documents** | Local volume (`LocalStorage`) + basic file checks | An S3-compatible `FileStorage` (e.g. in Frankfurt) and AI extraction of invoice data (hook: `operations/domain/shipping.py::basic_document_checks`) |
| **VAT** | 0% (`VAT_RATE_BP` on the billing service) | Confirm treatment per service with your tax adviser; add PDF invoices and export to your accounting tool |
| **Email** | Mailpit in development | Your SMTP provider (`SMTP_*` in `.env`) |

## Configuration

All services read environment variables (see `.env.example`). The important ones: `JWT_SECRET` (same for every service), `DATABASE_URL` (per service), `BROKER_URL` (`amqp://…` or `memory://`), `ROOT_PATH` (path prefix behind the gateway), `SEED_DEMO_DATA`, `TRACKING_WEBHOOK_TOKEN`, `SMTP_*`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
