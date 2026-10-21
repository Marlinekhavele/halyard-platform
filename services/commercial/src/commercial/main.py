"""Entry point of the Commercial service.

Run with ``uvicorn commercial.main:app``.
"""

import fastapi

from commercial import api
from commercial import models
from commercial.core import config
from commercial.core import seed
from halyard_common import service


def create_app(settings: config.Settings | None = None) -> fastapi.FastAPI:
    """Builds the Commercial app.

    Args:
        settings: Defaults to settings read from the environment.

    Returns:
        The application, with its runtime on ``app.state.runtime``.
    """
    settings = settings or config.Settings()
    runtime = service.ServiceRuntime(
        settings, models.Base.metadata, models.OutboxEvent
    )
    runtime.on_startup(seed.seed_reference_data)
    return service.create_app(
        runtime,
        title="Halyard Commercial",
        description=(
            "Ports, rates, surcharges, instant quotes, bookings and website"
            " leads."
        ),
        routers=[api.router],
    )


app = create_app()
service.configure_logging(app.state.runtime.settings)
