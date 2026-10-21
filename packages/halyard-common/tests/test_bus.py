"""Tests for halyard_common.bus."""

import pytest

from halyard_common import bus
from halyard_common import events


@pytest.fixture(name="memory_bus")
def fixture_memory_bus():
    bus.InMemoryBus.reset()
    yield bus.InMemoryBus()
    bus.InMemoryBus.reset()


def _envelope(event_type: str) -> events.EventEnvelope:
    return events.EventEnvelope(type=event_type, source="test", data={"a": 1})


async def test_delivers_to_matching_subscribers_only(memory_bus):
    received: list[str] = []

    async def handler(envelope: events.EventEnvelope) -> None:
        received.append(envelope.type)

    await memory_bus.subscribe("svc.events", ["billing.invoice_paid"], handler)

    await memory_bus.publish(_envelope("billing.invoice_paid"))
    await memory_bus.publish(_envelope("billing.invoice_issued"))

    assert received == ["billing.invoice_paid"]


async def test_topic_wildcards_match(memory_bus):
    received: list[str] = []

    async def handler(envelope: events.EventEnvelope) -> None:
        received.append(envelope.type)

    await memory_bus.subscribe("svc.events", ["operations.#"], handler)

    await memory_bus.publish(_envelope("operations.customs_hold"))
    await memory_bus.publish(_envelope("billing.invoice_paid"))

    assert received == ["operations.customs_hold"]


async def test_failing_handler_is_dead_lettered(memory_bus):
    async def broken(envelope: events.EventEnvelope) -> None:
        raise RuntimeError("boom")

    await memory_bus.subscribe("svc.events", ["x.y"], broken)

    await memory_bus.publish(_envelope("x.y"))

    [(queue, envelope, error)] = bus.InMemoryBus.dead_letters
    assert queue == "svc.events"
    assert envelope.type == "x.y"
    assert "boom" in error


async def test_instances_share_one_registry(memory_bus):
    received: list[str] = []

    async def handler(envelope: events.EventEnvelope) -> None:
        received.append(envelope.id)

    await memory_bus.subscribe("svc.events", ["x.y"], handler)
    envelope = _envelope("x.y")

    await bus.InMemoryBus().publish(envelope)

    assert received == [envelope.id]


def test_create_bus_picks_implementation():
    assert isinstance(bus.create_bus("memory://"), bus.InMemoryBus)
    assert isinstance(bus.create_bus("amqp://localhost/"), bus.RabbitBus)
    with pytest.raises(ValueError):
        bus.create_bus("kafka://localhost")
