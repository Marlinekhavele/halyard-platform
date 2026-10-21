# Changelog

## Unreleased: backend-only restructure

### Removed
- Frontend references removed from docker-compose (six frontend containers), CI (the npm job), the Makefile (`web`, `gen-api`), the dev server (static file serving) and the README.
- **Frontend moved** to its own repository, `halyard-web` (next to this one). Its `gen-api` script now fetches the OpenAPI specs from a running backend (`HALYARD_API`), and it has its own docker-compose and CI.
- The backend Docker network is now named `halyard` so the frontend stack can join the gateway.
- Stale setuptools `build/` folders deleted.

### Architecture
- **Layered `src/` layout with the repository pattern in every service.** Packages are named after the service (`commercial` instead of `commercial_service`), with one folder per layer and one file per entity or feature:
  - `main.py`: the `create_app(settings)` factory
  - `core/`: settings, plus seeding, file storage, mailer or password hashing where a service needs them
  - `api/`: one thin router per feature, and `deps.py` to build services per request
  - `services/`: business rules, one `<feature>_service.py` each
  - `repositories/`: database queries, one `<entity>_repository.py` each
  - `models/`: ORM models, one file per entity
  - `schemas/`: request and response models, one file per feature
  - `domain/`: pure logic with no I/O (commercial pricing and reference data, operations shipping rules)
  - `events/`: event consumers (operations, billing, notifications)
  - Each layer package re-exports its public names, so code reads `models.Quote` and `services.QuoteService`.
- **Tests split** into `tests/unit/` (services, repositories, domain rules) and `tests/integration/` (HTTP API, event consumers, migrations), sharing `tests/conftest.py`.
- **New shared modules in `halyard_common`:**
  - `repository.py`: a generic `Repository[Model]` base class
  - `errors.py`: domain errors, mapped to HTTP responses in one place
  - `dependencies.py`: request-scoped session and current-user lookups
  - `testing.py`: shared test helpers
- **Outbox:** `OutboxRepository` replaces the old `add_event()` function.
- **No more import-time globals.** Each app keeps its runtime on `app.state`, so every test gets an isolated app.
- **Swappable dependencies:**
  - Services take the current date as a parameter.
  - File storage is a `FileStorage` interface (`LocalStorage` is the disk version).
  - Email is a `Mailer` interface (`SmtpMailer` is the real one).
- **Typed responses:** the margin report and shipment stats now return Pydantic models instead of plain dicts. The JSON they produce is unchanged.

### Added
- **Alembic migrations per service** (`alembic.ini`, `migrations/`, initial revision `0001`), sharing `halyard_common.migrations`. Containers migrate on start; compose sets `AUTO_CREATE_TABLES=false`. New `make migrate` and `make migration svc=... m=...`. Checked on Postgres 16: upgrade, `alembic check` (no drift), downgrade and re-upgrade.
- **Migration drift tests** (`test_<service>_migrations.py`, via `testing.schema_drift`) fail when a model changes without a migration.
- **Logging** (`halyard_common.logs`): a request log line per request with status and duration; an `X-Request-ID` that is returned in each response and carried inside events as `correlation_id`, so one request can be traced across services; logs for staged and handled events and failed sign-ins. Readable text locally, JSON lines with `LOG_JSON=true` (on in docker-compose), level via `LOG_LEVEL`.
- **Coverage:** `.coveragerc` with branch coverage and a 90% floor (currently 96.5%), `make coverage`, and the HTML/XML reports as a CI artifact.
- **CI:** tests on Python 3.11, 3.12 and 3.13; a Postgres job that runs the end-to-end and concurrency tests and checks every service's migrations (upgrade, drift, downgrade, upgrade).
- **Production guards:** settings refuse to load in `production` or `staging` with the development JWT secret, a JWT secret shorter than 32 characters, or the default tracking-webhook token.

### Security and concurrency fixes
- **Double booking:** booking now claims the quote atomically (`UPDATE … WHERE status = 'open'`), so two simultaneous bookings of one quote give exactly one 201 and one 409. Before, both could succeed.
- **Duplicate reference numbers:** quote, booking, customer and invoice numbers are allocated under a PostgreSQL advisory lock, so simultaneous creates no longer collide and fail with a 500.
- **Downloads with non-Latin file names** (e.g. `发票.pdf`) returned 500, and quotes or line breaks in a name could break the header. `Content-Disposition` now has an ASCII fallback plus an RFC 5987 `filename*`.
- **Uploads** read at most the size limit + 1 byte instead of the whole file into memory.
- **Tracking webhook** compares its token in constant time.
- **`limit` parameters** on `/quotes` (1–200) and `/notifications` (1–100) are bounded; negative values used to mean "no limit" on SQLite and a 500 on Postgres.

### Fixed
- **RabbitMQ first-start race.** Compose now starts consumers first (notifications → billing → operations → commercial, accounts) and waits for each to be healthy, so startup events are never published before their queues exist.
- **Dev mode dropped startup events.** The demo users were announced before the notifications service was listening, so no emails went out and ops approvals showed as "customer approved". Startup now has two phases (`prepare()` then `run()`): every service starts listening before any sends. The same bug existed in the original code.
- **Stray `./storage` folder.** Importing the operations app created it; `LocalStorage` now creates its folder on the first upload.
- **Deprecated status codes.** The error classes now use stdlib `http.HTTPStatus` instead of Starlette's deprecated constants.

### Changed behaviour
- An `ETA_CHANGED` event with no new date is now rejected even when the shipment is already closed (before, it was silently ignored).

### Code style (Google Python Style Guide)
- Whole-module imports, one import per line, Google docstrings everywhere, 80-character lines.
- New `ruff.toml` enforces these rules, except the module-import rule, which ruff can't check. CI has a new `lint` job.
- The demo seeder script (`scripts/seed_demo.py`) was rewritten in this style. Its six scenarios and API calls are the same.

### Tests
- Went from 12 to 217 tests (215 run on SQLite, 2 more on Postgres), all passing:

| Area | Tests |
| --- | --- |
| halyard-common | 48 |
| accounts | 25 |
| commercial | 51 |
| operations | 50 |
| billing | 18 |
| notifications | 21 |
| end-to-end | 4 (2 need Postgres) |

- Each service now tests its database queries, its business rules and its HTTP endpoints and event handling.
- Old per-file `sys.path` hacks were replaced by `--import-mode=importlib` in `pytest.ini`.
- The end-to-end test now also checks that ops actually receives the booking email (a regression check for the startup fix).

### Tooling and docs
- New `requirements-dev.txt`.
- New Makefile targets: `test-unit`, `test-e2e`, `lint`, `format`, `openapi`.
- `export_openapi.py` now writes to `docs/openapi/`.
- README rewritten for the backend-only layout, with the layering rules, style guide and testing sections. A RabbitMQ first-start event race is noted under production work.
- `.gitignore` now covers `**/build/` and `.ruff_cache/`.
