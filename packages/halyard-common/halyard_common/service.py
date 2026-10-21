"""Service runtime: wires database, bus, outbox relay and consumers into an app.

Every service exposes an app factory built on ``create_app``. The runtime is
stored on ``app.state.runtime`` so that request dependencies (see
``halyard_common.dependencies``) can reach it without module-level globals.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
import contextlib
import logging
from typing import Any

import fastapi
from fastapi.middleware import cors
import sqlalchemy as sa

from halyard_common import bus as bus_lib
from halyard_common import config
from halyard_common import db
from halyard_common import errors
from halyard_common import logs
from halyard_common import outbox
from halyard_common import telemetry

StartupHook = Callable[["ServiceRuntime"], Awaitable[None]]


def configure_logging(settings: config.ServiceSettings) -> None:
    """Configures process-wide logging from a service's settings.

    Args:
        settings: Supplies the level, format and service name.
    """
    logs.configure_logging(
        settings.log_level, settings.log_json, settings.service_name
    )


class ServiceRuntime:
    """Infrastructure of one running service.

    Attributes:
        settings: The service settings.
        metadata: The service's table metadata.
        db: The service's database.
        bus: The message bus.
        relay: The outbox relay, if the service publishes events.
        log: The service logger.
    """

    def __init__(
        self,
        settings: config.ServiceSettings,
        metadata: sa.MetaData,
        outbox_model: type[Any] | None = None,
    ) -> None:
        """Initialises the runtime without connecting to anything.

        Args:
            settings: The service settings.
            metadata: The service's table metadata.
            outbox_model: The outbox ORM class, if the service publishes.
        """
        self.settings = settings
        self.metadata = metadata
        self.db = db.Database(settings.database_url)
        self.bus = bus_lib.create_bus(
            settings.broker_url, settings.events_exchange
        )
        self.relay = (
            outbox.OutboxRelay(
                self.db, outbox_model, self.bus, settings.outbox_poll_seconds
            )
            if outbox_model
            else None
        )
        self._consumers: list[tuple[list[str], bus_lib.Handler]] = []
        self._startup: list[StartupHook] = []
        self.log = logging.getLogger(f"halyard.{settings.service_name}")

    def consume(
        self, routing_keys: list[str], handler: bus_lib.Handler
    ) -> None:
        """Subscribes a handler to event types when the service starts.

        Args:
            routing_keys: Event types to receive.
            handler: The bus handler.
        """
        self._consumers.append((routing_keys, handler))

    def on_startup(self, hook: StartupHook) -> StartupHook:
        """Registers a coroutine to run on startup, for example seeding.

        Args:
            hook: Called with this runtime after tables and bus are ready.

        Returns:
            The hook, so this can be used as a decorator.
        """
        self._startup.append(hook)
        return hook

    async def prepare(self) -> None:
        """Phase 1: creates tables, connects the bus and subscribes consumers.

        Nothing is published yet. When several services share one process,
        prepare all of them before running any, so that events published on
        startup (such as seeded users) reach every subscriber.
        """
        if self.settings.auto_create_tables:
            await self.db.create_all(self.metadata)
        await self.bus.connect()
        for keys, handler in self._consumers:
            await self.bus.subscribe(
                f"{self.settings.service_name}.events", keys, handler
            )

    async def run(self) -> None:
        """Phase 2: runs startup hooks and starts publishing the outbox."""
        for hook in self._startup:
            await hook(self)
        if self.relay:
            self.relay.start()
        self.log.info("%s started", self.settings.service_name)

    async def start(self) -> None:
        """Prepares and runs the service."""
        await self.prepare()
        await self.run()

    async def stop(self) -> None:
        """Stops the relay and closes the bus and database."""
        if self.relay:
            await self.relay.stop()
        await self.bus.close()
        await self.db.dispose()


def create_app(
    runtime: ServiceRuntime,
    title: str,
    description: str,
    routers: Sequence[fastapi.APIRouter],
) -> fastapi.FastAPI:
    """Builds the FastAPI app for a service.

    Args:
        runtime: The service runtime, started and stopped with the app.
        title: OpenAPI title.
        description: OpenAPI description.
        routers: The service's API routers.

    Returns:
        The configured application.
    """
    settings = runtime.settings

    @contextlib.asynccontextmanager
    async def lifespan(_: fastapi.FastAPI) -> AsyncIterator[None]:
        await runtime.start()
        yield
        await runtime.stop()

    app = fastapi.FastAPI(
        title=title,
        description=description,
        version="0.1.0",
        lifespan=lifespan,
        root_path=settings.root_path,
    )
    app.state.runtime = runtime
    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[logs.REQUEST_ID_HEADER],
    )
    # Added last, so it wraps everything else and sees every response.
    app.add_middleware(logs.RequestLoggingMiddleware)
    errors.install_error_handlers(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok", "service": settings.service_name}

    for router in routers:
        app.include_router(router)

    telemetry.setup_telemetry(
        app,
        settings.service_name,
        settings.otel_exporter_otlp_endpoint,
        runtime.db.engine,
    )
    return app
