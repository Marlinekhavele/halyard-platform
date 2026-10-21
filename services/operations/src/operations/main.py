"""Entry point of the Operations service.

Run with ``uvicorn operations.main:app``.
"""

import fastapi

from halyard_common import events
from halyard_common import outbox
from halyard_common import service
from operations import api
from operations import models
from operations.core import config
from operations.core import storage as storage_lib
from operations.events import handlers


def create_app(
    settings: config.Settings | None = None,
    storage: storage_lib.FileStorage | None = None,
) -> fastapi.FastAPI:
    """Builds the Operations app.

    Args:
        settings: Defaults to settings read from the environment.
        storage: Defaults to local storage under
            ``settings.document_storage_dir``.

    Returns:
        The application, with its runtime on ``app.state.runtime`` and its
        document storage on ``app.state.storage``.
    """
    settings = settings or config.Settings()
    runtime = service.ServiceRuntime(
        settings, models.Base.metadata, models.OutboxEvent
    )
    runtime.consume(
        [
            events.EventType.BOOKING_CONFIRMED,
            events.EventType.BOOKING_CANCELLED,
        ],
        outbox.idempotent_consumer(
            runtime.db,
            models.ProcessedEvent,
            handlers.EventHandlers(settings).handlers(),
        ),
    )
    app = service.create_app(
        runtime,
        title="Halyard Operations",
        description=(
            "Shipments, containers, milestones, tracking events and documents."
        ),
        routers=[api.router],
    )
    app.state.storage = storage or storage_lib.LocalStorage(
        settings.document_storage_dir
    )
    return app


app = create_app()
service.configure_logging(app.state.runtime.settings)
