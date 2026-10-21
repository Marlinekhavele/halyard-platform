"""Alembic support shared by every service.

Each service has an ``alembic.ini`` and a ``migrations/`` folder whose
``env.py`` only calls ``run_migrations`` with the service's metadata and
settings. Usage, from a service folder::

    alembic upgrade head
    alembic revision --autogenerate -m "add invoice notes"

The database URL comes from the service settings (``DATABASE_URL`` or the
service-specific variable) unless ``sqlalchemy.url`` is set in the Alembic
config, which tests use.
"""

import asyncio
from logging import config as logging_config

from alembic import context
import sqlalchemy as sa
from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import config

# SQLite cannot ALTER most things; batch mode recreates tables instead.
_OPTIONS = {"render_as_batch": True, "compare_type": True}


def _run_with_connection(
    connection: sa.Connection, metadata: sa.MetaData
) -> None:
    context.configure(
        connection=connection, target_metadata=metadata, **_OPTIONS
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online(url: str, metadata: sa.MetaData) -> None:
    engine = sa_asyncio.create_async_engine(url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_with_connection, metadata)
    finally:
        await engine.dispose()


def run_migrations(
    metadata: sa.MetaData, settings: config.ServiceSettings
) -> None:
    """Runs Alembic for one service; call this from its ``env.py``.

    Args:
        metadata: The service's table metadata (autogenerate target).
        settings: The service settings, used for the database URL.
    """
    if context.config.config_file_name:
        logging_config.fileConfig(
            context.config.config_file_name, disable_existing_loggers=False
        )
    url = (
        context.config.get_main_option("sqlalchemy.url")
        or settings.database_url
    )
    if context.is_offline_mode():
        context.configure(
            url=url, target_metadata=metadata, literal_binds=True, **_OPTIONS
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    asyncio.run(_run_online(url, metadata))
