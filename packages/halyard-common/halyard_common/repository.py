"""Generic repository base class.

A repository is the only place that talks to the database for one aggregate.
Services receive repositories, call intention-revealing methods on them and
decide when to commit. Repositories never commit; they only ``flush`` so that
generated values such as primary keys become available.
"""

from collections.abc import Iterable, Sequence
from typing import Any, ClassVar, Generic, TypeVar
import zlib

import sqlalchemy as sa
from sqlalchemy.ext import asyncio as sa_asyncio

ModelT = TypeVar("ModelT")


async def lock_sequence(session: sa_asyncio.AsyncSession, name: str) -> None:
    """Serialises allocation of a sequence of numbers until commit.

    Reference numbers such as ``INV-2026-00001`` are derived from a count of
    existing rows. Two transactions counting at the same time would pick the
    same number. On PostgreSQL this takes a transaction-scoped advisory lock,
    so the second transaction waits until the first commits. SQLite already
    allows only one writer at a time, so nothing is needed there.

    Args:
        session: The transaction that will insert the numbered row.
        name: Identifies the sequence, for example ``"invoice-number"``.
    """
    if session.bind.dialect.name != "postgresql":
        return
    key = zlib.crc32(name.encode())
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
    )


class Repository(Generic[ModelT]):
    """Common persistence operations for a single ORM model.

    Subclasses set ``model`` and add query methods specific to their aggregate.

    Attributes:
        model: The ORM class this repository manages.
    """

    model: ClassVar[type[Any]]

    def __init__(self, session: sa_asyncio.AsyncSession) -> None:
        """Initialises the repository.

        Args:
            session: The unit of work shared with the calling service.
        """
        self._session = session

    @property
    def session(self) -> sa_asyncio.AsyncSession:
        """The session this repository works in."""
        return self._session

    async def get(self, entity_id: Any) -> ModelT | None:
        """Loads one entity by primary key.

        Args:
            entity_id: The primary key value.

        Returns:
            The entity, or None if it does not exist.
        """
        return await self._session.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        """Stages a new entity and flushes it so its defaults are populated.

        Args:
            entity: The entity to persist.

        Returns:
            The same entity, now attached to the session.
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def add_all(self, entities: Iterable[ModelT]) -> None:
        """Stages several new entities and flushes them.

        Args:
            entities: The entities to persist.
        """
        self._session.add_all(list(entities))
        await self._session.flush()

    async def count(self, *criteria: Any) -> int:
        """Counts entities, optionally filtered.

        Args:
            *criteria: SQLAlchemy filter expressions combined with AND.

        Returns:
            The number of matching rows.
        """
        stmt = sa.select(sa.func.count()).select_from(self.model)
        if criteria:
            stmt = stmt.where(*criteria)
        return (await self._session.scalar(stmt)) or 0

    async def _scalars(self, stmt: sa.Select[Any]) -> Sequence[ModelT]:
        """Runs a select statement and returns its scalar results.

        Args:
            stmt: The statement to execute.

        Returns:
            All rows of the first column.
        """
        return (await self._session.scalars(stmt)).all()

    async def _scalar(self, stmt: sa.Select[Any]) -> ModelT | None:
        """Runs a select statement and returns the first scalar result.

        Args:
            stmt: The statement to execute.

        Returns:
            The first row's first column, or None.
        """
        return await self._session.scalar(stmt)
