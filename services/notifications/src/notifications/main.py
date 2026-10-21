"""Entry point of the Notifications service.

Notifications turns business events into emails and in-app alerts. Run with
``uvicorn notifications.main:app``.
"""

import fastapi

from halyard_common import outbox
from halyard_common import service
from notifications import api
from notifications import models
from notifications.core import config
from notifications.core import mailer as mailer_lib
from notifications.events import handlers


def create_app(
    settings: config.Settings | None = None,
    mailer: mailer_lib.Mailer | None = None,
) -> fastapi.FastAPI:
    """Builds the Notifications app.

    Args:
        settings: Defaults to settings read from the environment.
        mailer: Defaults to SMTP using ``settings``.

    Returns:
        The application, with its runtime on ``app.state.runtime`` and its
        mailer on ``app.state.mailer``.
    """
    settings = settings or config.Settings()
    mailer = mailer or mailer_lib.SmtpMailer(settings)
    runtime = service.ServiceRuntime(settings, models.Base.metadata)
    event_handlers = handlers.EventHandlers(mailer).handlers()
    runtime.consume(
        list(event_handlers),
        outbox.idempotent_consumer(
            runtime.db, models.ProcessedEvent, event_handlers
        ),
    )
    app = service.create_app(
        runtime,
        title="Halyard Notifications",
        description=(
            "Emails and in-app alerts driven by events from the other services."
        ),
        routers=[api.router],
    )
    app.state.mailer = mailer
    return app


app = create_app()
service.configure_logging(app.state.runtime.settings)
