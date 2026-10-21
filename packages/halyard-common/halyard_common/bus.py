"""Message bus: RabbitMQ in deployments, in-process for tests and local runs.

Topology (RabbitMQ):
  - One durable topic exchange (default ``halyard.events``); the routing key
    is the event type.
  - One durable queue per consuming service (``<service>.events``), bound to
    the event types it handles.
  - Failed messages are dead-lettered to ``halyard.dlx`` and end up in
    ``<service>.events.dead`` for inspection.
"""

import abc
import asyncio
from collections.abc import Awaitable, Callable
import dataclasses
import fnmatch
import json
import logging
from typing import Any

from halyard_common import events

_log = logging.getLogger("halyard.bus")

Handler = Callable[[events.EventEnvelope], Awaitable[None]]


class MessageBus(abc.ABC):
    """Publishes events and delivers them to subscribed handlers."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Opens the connection to the broker."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Closes the connection to the broker."""

    @abc.abstractmethod
    async def publish(self, envelope: events.EventEnvelope) -> None:
        """Publishes one event.

        Args:
            envelope: The event to publish.
        """

    @abc.abstractmethod
    async def subscribe(
        self, queue: str, routing_keys: list[str], handler: Handler
    ) -> None:
        """Delivers events matching the routing keys to a handler.

        Args:
            queue: Name of the consuming service's queue.
            routing_keys: Event types (topic patterns) to receive.
            handler: Coroutine called once per event.
        """


@dataclasses.dataclass
class _Subscription:
    queue: str
    routing_keys: list[str]
    handler: Handler

    def matches(self, key: str) -> bool:
        # RabbitMQ topic wildcards: "*" one word, "#" any. fnmatch is close
        # enough for our keys.
        return any(
            fnmatch.fnmatch(key, rk.replace("#", "*"))
            for rk in self.routing_keys
        )


class InMemoryBus(MessageBus):
    """Delivers events to subscribers in the same process.

    All instances share one registry, so several services started in one
    process (the dev server or the end-to-end test) can talk to each other.

    Attributes:
        dead_letters: ``(queue, envelope, error)`` for every failed delivery.
    """

    _subscriptions: list[_Subscription] = []
    dead_letters: list[tuple[str, events.EventEnvelope, str]] = []

    async def connect(self) -> None:
        """Does nothing; there is no broker."""

    async def close(self) -> None:
        """Does nothing; there is no broker."""

    @classmethod
    def reset(cls) -> None:
        """Removes every subscription and dead letter."""
        cls._subscriptions = []
        cls.dead_letters = []

    async def publish(self, envelope: events.EventEnvelope) -> None:
        """Delivers the event to every matching subscriber.

        Args:
            envelope: The event to publish.
        """
        # Round-trip through JSON so tests catch anything that would not
        # survive the wire.
        wire = events.EventEnvelope.model_validate_json(
            envelope.model_dump_json()
        )
        for sub in list(self._subscriptions):
            if not sub.matches(wire.type):
                continue
            try:
                await sub.handler(wire)
            except Exception as exc:  # pylint: disable=broad-except
                _log.exception(
                    "handler for %s in %s failed", wire.type, sub.queue
                )
                self.dead_letters.append((sub.queue, wire, repr(exc)))

    async def subscribe(
        self, queue: str, routing_keys: list[str], handler: Handler
    ) -> None:
        """Registers a handler for matching events.

        Args:
            queue: Name of the consuming service's queue.
            routing_keys: Event types (topic patterns) to receive.
            handler: Coroutine called once per event.
        """
        self._subscriptions.append(_Subscription(queue, routing_keys, handler))


class RabbitBus(MessageBus):
    """Message bus backed by a RabbitMQ topic exchange."""

    def __init__(
        self, url: str, exchange: str = "halyard.events", prefetch: int = 20
    ) -> None:
        """Initialises the bus without connecting.

        Args:
            url: AMQP connection URL.
            exchange: Name of the topic exchange.
            prefetch: Unacknowledged messages allowed per consumer.
        """
        self.url = url
        self.exchange_name = exchange
        self.prefetch = prefetch
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None
        self._dlx: Any = None

    async def connect(self) -> None:
        """Connects, retrying while the broker starts up.

        Raises:
            RuntimeError: The broker was not reachable after 30 attempts.
        """
        import aio_pika  # pylint: disable=import-outside-toplevel

        for attempt in range(30):
            try:
                self._connection = await aio_pika.connect_robust(self.url)
                break
            except Exception as exc:  # pylint: disable=broad-except
                _log.warning(
                    "RabbitMQ not ready (%s), retrying (%s/30)",
                    exc,
                    attempt + 1,
                )
                await asyncio.sleep(2)
        else:
            raise RuntimeError(f"Could not connect to RabbitMQ at {self.url}")

        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch)
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self._dlx = await self._channel.declare_exchange(
            "halyard.dlx", aio_pika.ExchangeType.DIRECT, durable=True
        )

    async def close(self) -> None:
        """Closes the connection if open."""
        if self._connection:
            await self._connection.close()

    async def publish(self, envelope: events.EventEnvelope) -> None:
        """Publishes a persistent message routed by event type.

        Args:
            envelope: The event to publish.
        """
        import aio_pika  # pylint: disable=import-outside-toplevel

        message = aio_pika.Message(
            body=envelope.model_dump_json().encode(),
            content_type="application/json",
            message_id=envelope.id,
            type=envelope.type,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=envelope.type)

    async def subscribe(
        self, queue: str, routing_keys: list[str], handler: Handler
    ) -> None:
        """Declares the queue and its dead-letter queue and starts consuming.

        Args:
            queue: Name of the consuming service's queue.
            routing_keys: Event types (topic patterns) to receive.
            handler: Coroutine called once per event.
        """
        dead_queue = await self._channel.declare_queue(
            f"{queue}.dead", durable=True
        )
        await dead_queue.bind(self._dlx, routing_key=queue)

        q = await self._channel.declare_queue(
            queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "halyard.dlx",
                "x-dead-letter-routing-key": queue,
            },
        )
        for key in routing_keys:
            await q.bind(self._exchange, routing_key=key)

        async def on_message(message: Any) -> None:
            try:
                envelope = events.EventEnvelope.model_validate(
                    json.loads(message.body)
                )
                await handler(envelope)
            except Exception:  # pylint: disable=broad-except
                _log.exception(
                    "handler failed for message %s; dead-lettering",
                    message.message_id,
                )
                await message.reject(requeue=False)
            else:
                await message.ack()

        await q.consume(on_message)


def create_bus(url: str, exchange: str = "halyard.events") -> MessageBus:
    """Creates the bus implementation matching a broker URL.

    Args:
        url: ``memory://`` or an ``amqp://`` URL.
        exchange: Name of the topic exchange (RabbitMQ only).

    Returns:
        A message bus.

    Raises:
        ValueError: The URL scheme is not supported.
    """
    if url.startswith("memory"):
        return InMemoryBus()
    if url.startswith("amqp"):
        return RabbitBus(url, exchange)
    raise ValueError(f"Unsupported broker url: {url}")
