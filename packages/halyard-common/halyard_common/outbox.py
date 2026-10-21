"""Transactional outbox and idempotent inbox.

Outbox: a service never publishes directly. ``OutboxRepository`` writes the
event into the service's own ``outbox`` table in the same transaction as the
business change. ``OutboxRelay`` then publishes it and marks it sent. If the
broker is down nothing is lost; events go out when it is back.

Inbox: consumers record each processed event id, so a redelivered message is
ignored.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import datetime
import logging
import time
from typing import Any

import pydantic
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import bus as bus_lib
from halyard_common import db
from halyard_common import events
from halyard_common import logs

_log = logging.getLogger("halyard.outbox")

EventHandler = Callable[
    [sa_asyncio.AsyncSession, events.EventEnvelope], Awaitable[None]
]


class OutboxMixin:
    """Columns of the ``outbox`` table.

    Usage in each service::

        class OutboxEvent(outbox.OutboxMixin, Base):
            __tablename__ = "outbox"
    """

    id: orm.Mapped[str] = orm.mapped_column(
        sa.String(36), primary_key=True, default=db.new_id
    )
    type: orm.Mapped[str] = orm.mapped_column(sa.String(80), index=True)
    payload: orm.Mapped[dict] = orm.mapped_column(sa.JSON)
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=db.utcnow, index=True
    )
    published_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True, index=True
    )
    attempts: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=0)
    last_error: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(500), nullable=True
    )


class ProcessedEventMixin:
    """Columns of the ``processed_events`` (inbox) table."""

    event_id: orm.Mapped[str] = orm.mapped_column(
        sa.String(36), primary_key=True
    )
    type: orm.Mapped[str] = orm.mapped_column(sa.String(80))
    processed_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=db.utcnow
    )


class OutboxRepository:
    """Stages events in the caller's transaction."""

    def __init__(
        self,
        session: sa_asyncio.AsyncSession,
        outbox_model: type[Any],
        source: str,
    ) -> None:
        """Initialises the repository.

        Args:
            session: The unit of work of the business change.
            outbox_model: The service's outbox ORM class.
            source: Name of the publishing service.
        """
        self._session = session
        self._model = outbox_model
        self._source = source

    def add(
        self, event_type: str, data: pydantic.BaseModel | dict[str, Any]
    ) -> events.EventEnvelope:
        """Stages an event. It is published by the relay after commit.

        Args:
            event_type: One of ``events.EventType``.
            data: The payload.

        Returns:
            The staged envelope.
        """
        payload = (
            data.model_dump(mode="json")
            if isinstance(data, pydantic.BaseModel)
            else data
        )
        envelope = events.EventEnvelope(
            type=event_type,
            source=self._source,
            data=payload,
            correlation_id=logs.correlation_id.get(),
        )
        self._session.add(
            self._model(
                id=envelope.id,
                type=event_type,
                payload=envelope.model_dump(mode="json"),
            )
        )
        _log.info(
            "event staged %s",
            event_type,
            extra={"event_type": event_type, "event_id": envelope.id},
        )
        return envelope


class OutboxRelay:
    """Publishes pending outbox rows in the background."""

    def __init__(
        self,
        database: db.Database,
        outbox_model: type[Any],
        bus: bus_lib.MessageBus,
        poll_seconds: float = 0.5,
        batch: int = 100,
    ) -> None:
        """Initialises the relay without starting it.

        Args:
            database: The service's database.
            outbox_model: The service's outbox ORM class.
            bus: Where to publish.
            poll_seconds: Pause between polls when nothing is pending.
            batch: Maximum rows published per flush.
        """
        self.db = database
        self.model = outbox_model
        self.bus = bus
        self.poll_seconds = poll_seconds
        self.batch = batch
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._lock = asyncio.Lock()

    async def flush(self) -> int:
        """Publishes pending events, oldest first.

        Stops at the first failure so ordering is preserved; the failed row
        records the error and is retried on the next flush.

        Returns:
            How many events were published.
        """
        async with self._lock:
            sent = 0
            async with self.db.sessionmaker() as session:
                stmt = (
                    sa.select(self.model)
                    .where(self.model.published_at.is_(None))
                    .order_by(self.model.created_at)
                    .limit(self.batch)
                )
                if self.db.is_postgres:
                    # Several replicas of a service can run the relay safely.
                    stmt = stmt.with_for_update(skip_locked=True)
                rows = (await session.execute(stmt)).scalars().all()
                for row in rows:
                    try:
                        await self.bus.publish(
                            events.EventEnvelope.model_validate(row.payload)
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        row.attempts += 1
                        row.last_error = repr(exc)[:500]
                        _log.warning("publishing %s failed: %s", row.id, exc)
                        break
                    row.published_at = db.utcnow()
                    sent += 1
                await session.commit()
            return sent

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                while await self.flush():
                    pass
            except Exception:  # pylint: disable=broad-except
                _log.exception("outbox relay error")
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.poll_seconds
                )
            except TimeoutError:
                pass

    def start(self) -> None:
        """Starts the background task on the running event loop."""
        # Fresh primitives bound to the running loop; the relay can restart.
        self._stopping = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        """Stops the background task and waits for it to finish."""
        self._stopping.set()
        if self._task:
            await self._task


def idempotent_consumer(
    database: db.Database,
    processed_model: type[Any],
    handlers: Mapping[str, EventHandler],
) -> bus_lib.Handler:
    """Wraps per-event-type handlers into one bus handler.

    Each event is handled in its own transaction and skipped if its id was
    already processed.

    Args:
        database: The consuming service's database.
        processed_model: The service's inbox ORM class.
        handlers: Handler per event type. Other types are ignored.

    Returns:
        A handler suitable for ``MessageBus.subscribe``.
    """

    async def consume(envelope: events.EventEnvelope) -> None:
        handler = handlers.get(envelope.type)
        if handler is None:
            return
        # Log under the id of the request that caused the event, so one
        # booking can be followed across services.
        token = logs.correlation_id.set(envelope.correlation_id or envelope.id)
        extra = {"event_type": envelope.type, "event_id": envelope.id}
        started = time.perf_counter()
        try:
            async with database.sessionmaker() as session:
                if await session.get(processed_model, envelope.id):
                    _log.info(
                        "skipping duplicate event %s",
                        envelope.type,
                        extra=extra,
                    )
                    return
                await handler(session, envelope)
                session.add(
                    processed_model(event_id=envelope.id, type=envelope.type)
                )
                await session.commit()
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            _log.info(
                "event handled %s",
                envelope.type,
                extra={**extra, "duration_ms": duration_ms},
            )
        finally:
            logs.correlation_id.reset(token)

    return consume
