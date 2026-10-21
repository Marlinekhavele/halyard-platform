"""Runs every Halyard service in one process, without Docker.

Each service is mounted under ``/api/<service>``, exactly like behind the
Traefik gateway, and they talk through the in-memory event bus. Handy for
local development, demos and the end-to-end test.

    python scripts/dev_server.py            # http://localhost:8080
    python scripts/dev_server.py --reset    # start from empty databases

By default each service gets its own SQLite file in ``.dev/``. Set
``ACCOUNTS_DATABASE_URL``, ``COMMERCIAL_DATABASE_URL``, ... to use Postgres.
"""

import argparse
from collections.abc import AsyncIterator
import contextlib
import importlib
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVICES = ["accounts", "commercial", "operations", "billing", "notifications"]


def prepare_environment(data_dir: pathlib.Path) -> None:
    """Points every service at local data and makes the packages importable.

    Existing environment variables win, so Postgres URLs can be supplied.

    Args:
        data_dir: Directory for SQLite files and uploaded documents.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("BROKER_URL", "memory://")
    os.environ.setdefault("DOCUMENT_STORAGE_DIR", str(data_dir / "documents"))
    for name in SERVICES:
        os.environ.setdefault(
            f"{name.upper()}_DATABASE_URL",
            f"sqlite+aiosqlite:///{data_dir / name}.db",
        )
        sys.path.insert(0, str(ROOT / "services" / name / "src"))
    sys.path.insert(0, str(ROOT / "packages" / "halyard-common"))


async def start_all(runtimes) -> None:
    """Starts several service runtimes that share one in-memory bus.

    Every service subscribes before any service seeds or publishes;
    otherwise events published on startup (for example the demo users from
    Accounts) would be lost for services that start later.

    Args:
        runtimes: The ``ServiceRuntime`` of every service.
    """
    for runtime in runtimes:
        await runtime.prepare()
    for runtime in runtimes:
        await runtime.run()


def build_app():
    """Builds one FastAPI app with every service mounted under ``/api``.

    Mounted sub-applications do not run their own lifespan, so this app
    starts and stops every service runtime itself (see ``start_all``).

    Returns:
        The combined app. ``app.state.services`` maps service name to app.
    """
    import fastapi  # pylint: disable=import-outside-toplevel

    services = {
        name: importlib.import_module(f"{name}.main").create_app()
        for name in SERVICES
    }
    runtimes = [service_app.state.runtime for service_app in services.values()]

    @contextlib.asynccontextmanager
    async def lifespan(_: fastapi.FastAPI) -> AsyncIterator[None]:
        await start_all(runtimes)
        yield
        for runtime in reversed(runtimes):
            await runtime.stop()

    app = fastapi.FastAPI(
        title="Halyard (all services)", lifespan=lifespan, redoc_url=None
    )
    app.state.services = services
    for name, service_app in services.items():
        app.mount(f"/api/{name}", service_app)

    def openapi_schema() -> dict:
        # One Swagger UI at /docs for every service, built on first request.
        if app.openapi_schema is None:
            app.openapi_schema = combined_openapi(services)
        return app.openapi_schema

    app.openapi = openapi_schema
    return app


def combined_openapi(services: dict) -> dict:
    """Merges every service's OpenAPI document into one.

    Args:
        services: Service name to its FastAPI app.

    Returns:
        One OpenAPI document with gateway paths such as ``/api/billing/...``.
    """
    from halyard_common import (
        openapi,  # pylint: disable=import-outside-toplevel
    )

    return openapi.merge(
        {name: service_app.openapi() for name, service_app in services.items()},
        title="Halyard API",
        description=(
            "All Halyard services in one place. Sign in with"
            " `POST /api/accounts/auth/login`, then use **Authorize** with the"
            " access token; it works for every service.\n\n"
            "Demo users: `anna@nordwerk.example` / `demo1234` (customer),"
            " `ops@halyard.example` / `halyard-ops` (operations)."
        ),
    )


def main() -> None:
    """Parses arguments and serves the combined app with uvicorn."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data", default=str(ROOT / ".dev"))
    parser.add_argument(
        "--reset", action="store_true", help="delete local SQLite data first"
    )
    args = parser.parse_args()

    data_dir = pathlib.Path(args.data)
    if args.reset and data_dir.exists():
        shutil.rmtree(data_dir)
    prepare_environment(data_dir)
    # pylint: disable=import-outside-toplevel
    import uvicorn

    from halyard_common import config
    from halyard_common import logs

    app = build_app()
    # Every service shares this process, so label the logs accordingly.
    settings = config.ServiceSettings()
    logs.configure_logging(settings.log_level, settings.log_json, "all-in-one")
    # Requests are logged by RequestLoggingMiddleware; uvicorn's own access
    # log would print every request a second time.
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
