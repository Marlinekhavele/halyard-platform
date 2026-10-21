"""Entry point of the Billing service.

Run with ``uvicorn billing.main:app``.
"""

import fastapi

from billing import api
from billing import models
from billing.core import config
from billing.events import handlers
from halyard_common import outbox
from halyard_common import service


def create_app(settings: config.Settings | None = None) -> fastapi.FastAPI:
    """Builds the Billing app.

    Args:
        settings: Defaults to settings read from the environment.

    Returns:
        The application, with its runtime on ``app.state.runtime``.
    """
    settings = settings or config.Settings()
    runtime = service.ServiceRuntime(
        settings, models.Base.metadata, models.OutboxEvent
    )
    event_handlers = handlers.EventHandlers(settings).handlers()
    runtime.consume(
        list(event_handlers),
        outbox.idempotent_consumer(
            runtime.db, models.ProcessedEvent, event_handlers
        ),
    )
    return service.create_app(
        runtime,
        title="Halyard Billing",
        description=(
            "Customer invoices, partner costs and gross profit per shipment."
        ),
        routers=[api.router],
    )


app = create_app()
service.configure_logging(app.state.runtime.settings)
