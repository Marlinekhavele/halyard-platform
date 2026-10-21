"""Database engine, declarative base factory and common column mixins."""

import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sa_asyncio

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime.datetime:
    """Returns the current time as a timezone-aware UTC datetime."""
    return datetime.datetime.now(datetime.UTC)


def new_id() -> str:
    """Returns a new random UUID4 string for use as a primary key."""
    return str(uuid.uuid4())


def make_base() -> type[orm.DeclarativeBase]:
    """Creates a declarative base with its own metadata.

    Each service gets its own base, so it only ever creates its own tables.

    Returns:
        A new declarative base class.
    """

    class ServiceBase(orm.DeclarativeBase):
        metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

    return ServiceBase


class IdMixin:
    """Adds a UUID string primary key named ``id``."""

    id: orm.Mapped[str] = orm.mapped_column(
        sa.String(36), primary_key=True, default=new_id
    )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns."""

    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=utcnow
    )
    updated_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Database:
    """Owns the async engine and session factory of one service.

    Attributes:
        url: The SQLAlchemy database URL.
        engine: The async engine.
        sessionmaker: Factory for new sessions.
    """

    def __init__(self, url: str, echo: bool = False) -> None:
        """Initialises the engine.

        Args:
            url: SQLAlchemy async database URL.
            echo: Log every SQL statement.
        """
        kwargs: dict = {"echo": echo}
        if url.startswith("postgresql"):
            kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
        self.url = url
        self.engine: sa_asyncio.AsyncEngine = sa_asyncio.create_async_engine(
            url, **kwargs
        )
        self.sessionmaker = sa_asyncio.async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @property
    def is_postgres(self) -> bool:
        """Whether the database is PostgreSQL."""
        return self.url.startswith("postgresql")

    async def create_all(self, metadata: sa.MetaData) -> None:
        """Creates every table in the metadata that does not exist yet.

        Args:
            metadata: The service's table metadata.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def drop_all(self, metadata: sa.MetaData) -> None:
        """Drops every table in the metadata.

        Args:
            metadata: The service's table metadata.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)

    async def dispose(self) -> None:
        """Closes all pooled connections."""
        await self.engine.dispose()
