"""Tests for the repository base class, the outbox and the inbox."""

import pytest
import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import bus
from halyard_common import db
from halyard_common import events
from halyard_common import outbox
from halyard_common import repository
from halyard_common import testing

Base = db.make_base()


class Widget(db.IdMixin, db.TimestampMixin, Base):
    """A toy model for exercising the repository base class."""

    __tablename__ = "widgets"

    name: orm.Mapped[str] = orm.mapped_column(sa.String(50))


class OutboxEvent(outbox.OutboxMixin, Base):
    """Toy outbox table."""

    __tablename__ = "outbox"


class ProcessedEvent(outbox.ProcessedEventMixin, Base):
    """Toy inbox table."""

    __tablename__ = "processed_events"


class WidgetRepository(repository.Repository[Widget]):
    """Repository under test."""

    model = Widget


@pytest.fixture(name="url")
def fixture_url(tmp_path) -> str:
    return testing.sqlite_url(tmp_path)


@pytest.fixture(name="session")
async def fixture_session(url):
    async with testing.database_session(url, Base.metadata) as session:
        yield session


@pytest.fixture(name="memory_bus")
def fixture_memory_bus():
    bus.InMemoryBus.reset()
    yield bus.InMemoryBus()
    bus.InMemoryBus.reset()


async def test_repository_add_assigns_id_and_get_loads_it(session):
    widgets = WidgetRepository(session)

    widget = await widgets.add(Widget(name="anchor"))

    assert widget.id
    assert (await widgets.get(widget.id)).name == "anchor"
    assert await widgets.get("missing") is None


async def test_repository_count_with_and_without_criteria(session):
    widgets = WidgetRepository(session)
    await widgets.add_all([Widget(name="a"), Widget(name="b")])

    assert await widgets.count() == 2
    assert await widgets.count(Widget.name == "a") == 1


async def test_outbox_repository_stages_envelope_in_transaction(session):
    staged = outbox.OutboxRepository(session, OutboxEvent, "svc").add(
        events.EventType.INVOICE_PAID,
        events.InvoicePaid(
            invoice_id="i1", number="INV-1", company_id="c1", total_cents=100
        ),
    )
    await session.commit()

    row = await session.get(OutboxEvent, staged.id)
    assert row.type == events.EventType.INVOICE_PAID
    assert row.published_at is None
    assert row.payload["source"] == "svc"
    assert row.payload["data"]["total_cents"] == 100


async def test_relay_publishes_pending_events_once(url, memory_bus):
    database = db.Database(url)
    await database.create_all(Base.metadata)
    received: list[str] = []

    async def handler(envelope: events.EventEnvelope) -> None:
        received.append(envelope.id)

    await memory_bus.subscribe("svc.events", ["#"], handler)
    async with database.sessionmaker() as session:
        staged = outbox.OutboxRepository(session, OutboxEvent, "svc").add(
            "x.y", {"k": "v"}
        )
        await session.commit()
    relay = outbox.OutboxRelay(database, OutboxEvent, memory_bus)

    assert await relay.flush() == 1
    assert await relay.flush() == 0
    assert received == [staged.id]
    async with database.sessionmaker() as session:
        assert (await session.get(OutboxEvent, staged.id)).published_at
    await database.dispose()


async def test_relay_records_failures_and_retries(url):
    database = db.Database(url)
    await database.create_all(Base.metadata)

    class FlakyBus(bus.InMemoryBus):
        fail = True

        async def publish(self, envelope):
            if self.fail:
                raise ConnectionError("broker down")

    flaky = FlakyBus()
    async with database.sessionmaker() as session:
        staged = outbox.OutboxRepository(session, OutboxEvent, "svc").add(
            "x.y", {}
        )
        await session.commit()
    relay = outbox.OutboxRelay(database, OutboxEvent, flaky)

    assert await relay.flush() == 0
    async with database.sessionmaker() as session:
        row = await session.get(OutboxEvent, staged.id)
        assert row.attempts == 1
        assert "broker down" in row.last_error

    flaky.fail = False
    assert await relay.flush() == 1
    await database.dispose()


async def test_idempotent_consumer_skips_redelivered_events(url):
    database = db.Database(url)
    await database.create_all(Base.metadata)
    calls: list[str] = []

    async def on_widget(session, envelope):
        calls.append(envelope.id)
        session.add(Widget(name=envelope.data["name"]))

    consume = outbox.idempotent_consumer(
        database, ProcessedEvent, {"widget.made": on_widget}
    )
    envelope = events.EventEnvelope(
        type="widget.made", source="t", data={"name": "w"}
    )

    await consume(envelope)
    await consume(envelope)
    await consume(events.EventEnvelope(type="other", source="t", data={}))

    assert calls == [envelope.id]
    async with database.sessionmaker() as session:
        assert await WidgetRepository(session).count() == 1
    await database.dispose()
