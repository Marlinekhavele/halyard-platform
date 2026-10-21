"""Helpers for service test suites.

These live in the shared package so every service's tests build apps, tokens
and databases the same way.
"""

from collections.abc import AsyncIterator
import contextlib
import pathlib

import fastapi
import httpx
import sqlalchemy as sa
from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import auth
from halyard_common import bus
from halyard_common import config
from halyard_common import db

OPS_COMPANY_ID = "company-halyard"
CUSTOMER_COMPANY_ID = "company-customer"
OTHER_COMPANY_ID = "company-other"


def sqlite_url(directory: pathlib.Path, name: str = "test") -> str:
    """Returns an async SQLite URL for a file in a directory.

    Args:
        directory: Usually pytest's ``tmp_path``.
        name: File name without extension.

    Returns:
        The database URL.
    """
    return f"sqlite+aiosqlite:///{directory / name}.db"


def make_user(
    role: str = "customer_admin",
    company_id: str = CUSTOMER_COMPANY_ID,
    user_id: str | None = None,
    email: str | None = None,
) -> auth.CurrentUser:
    """Builds an authenticated user for tests.

    Args:
        role: The user's role.
        company_id: The user's company.
        user_id: Defaults to a new id.
        email: Defaults to an address derived from the role.

    Returns:
        The user.
    """
    return auth.CurrentUser(
        id=user_id or db.new_id(),
        company_id=company_id,
        email=email or f"{role}@{company_id}.example",
        name=role.replace("_", " ").title(),
        role=role,
    )


def ops_user() -> auth.CurrentUser:
    """Returns an ops user of the Halyard company."""
    return make_user(role="ops", company_id=OPS_COMPANY_ID)


def customer_user(company_id: str = CUSTOMER_COMPANY_ID) -> auth.CurrentUser:
    """Returns a customer admin of a company.

    Args:
        company_id: The customer's company.

    Returns:
        The user.
    """
    return make_user(role="customer_admin", company_id=company_id)


def auth_headers(
    settings: config.ServiceSettings, user: auth.CurrentUser
) -> dict[str, str]:
    """Returns an ``Authorization`` header for a user.

    Args:
        settings: The settings the app under test verifies tokens with.
        user: The user to sign in as.

    Returns:
        The request headers.
    """
    token = auth.create_access_token(settings, user)
    return {"Authorization": f"Bearer {token}"}


def schema_drift(
    alembic_ini: pathlib.Path, url: str, metadata: sa.MetaData
) -> list:
    """Migrates an empty database to head and compares it with the models.

    Call from a synchronous test: Alembic runs its own event loop.

    Args:
        alembic_ini: The service's ``alembic.ini``.
        url: An empty database, usually from ``sqlite_url``.
        metadata: The service's table metadata.

    Returns:
        Alembic's list of differences; empty when migrations match models.
    """
    # pylint: disable=import-outside-toplevel
    from alembic import autogenerate
    from alembic import command
    from alembic import config as alembic_config
    from alembic.runtime import migration

    cfg = alembic_config.Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    sync_url = url.replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = sa.create_engine(sync_url)
    try:
        with engine.connect() as connection:
            ctx = migration.MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            return autogenerate.compare_metadata(ctx, metadata)
    finally:
        engine.dispose()


@contextlib.asynccontextmanager
async def database_session(
    url: str, metadata: sa.MetaData
) -> AsyncIterator[sa_asyncio.AsyncSession]:
    """Creates a fresh database and yields one session on it.

    Use for repository and service tests that do not need the HTTP layer.

    Args:
        url: Database URL, usually from ``sqlite_url``.
        metadata: The service's table metadata.

    Yields:
        An open session. The engine is disposed afterwards.
    """
    database = db.Database(url)
    await database.create_all(metadata)
    try:
        async with database.sessionmaker() as session:
            yield session
    finally:
        await database.dispose()


@contextlib.asynccontextmanager
async def running_client(
    app: fastapi.FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Starts an app's runtime and yields an HTTP client bound to it.

    The in-memory bus registry is reset first so tests do not share
    subscriptions.

    Args:
        app: An app built by a service's ``create_app``.

    Yields:
        A client that sends requests straight to the app.
    """
    bus.InMemoryBus.reset()
    runtime = app.state.runtime
    await runtime.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
    finally:
        await runtime.stop()
        bus.InMemoryBus.reset()
