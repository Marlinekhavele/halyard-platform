"""Entry point of the Accounts service.

Run with ``uvicorn accounts.main:app``.
"""

import fastapi

from accounts import api
from accounts import models
from accounts.core import config
from accounts.core import seed
from halyard_common import service


def create_app(settings: config.Settings | None = None) -> fastapi.FastAPI:
    """Builds the Accounts app.

    Args:
        settings: Defaults to settings read from the environment.

    Returns:
        The application, with its runtime on ``app.state.runtime``.
    """
    settings = settings or config.Settings()
    runtime = service.ServiceRuntime(
        settings, models.Base.metadata, models.OutboxEvent
    )
    runtime.on_startup(seed.seed_demo_data)
    return service.create_app(
        runtime,
        title="Halyard Accounts",
        description="Companies, users, sign-in and access tokens.",
        routers=[api.router],
    )


app = create_app()
service.configure_logging(app.state.runtime.settings)
