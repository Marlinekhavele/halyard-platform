"""FastAPI dependencies that build the use-case classes per request."""

from typing import Annotated

import fastapi

from halyard_common import dependencies
from notifications import services


def get_notification_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.NotificationService:
    """Builds the notification service for one request."""
    return services.NotificationService(session, request.app.state.mailer)


Notifications = Annotated[
    services.NotificationService, fastapi.Depends(get_notification_service)
]
