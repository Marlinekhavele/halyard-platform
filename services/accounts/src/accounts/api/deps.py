"""FastAPI dependencies that build the use-case classes per request."""

from typing import Annotated

import fastapi

from accounts import services
from halyard_common import dependencies


def get_account_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.AccountService:
    """Builds the account service for one request.

    Args:
        request: The incoming request.
        session: The request's database session.

    Returns:
        The service.
    """
    return services.AccountService(session, dependencies.get_settings(request))


Service = Annotated[
    services.AccountService, fastapi.Depends(get_account_service)
]
