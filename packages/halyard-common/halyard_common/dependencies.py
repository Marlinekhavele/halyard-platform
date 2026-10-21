"""FastAPI dependencies shared by every service.

Each app stores its ``ServiceRuntime`` on ``app.state.runtime``. The
dependencies below read it from the request, so routers carry no module-level
state and a fresh app (for example one per test) is fully isolated.
"""

from collections.abc import AsyncIterator
from typing import Annotated

import fastapi
from fastapi import security
from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import auth
from halyard_common import config
from halyard_common import errors
from halyard_common import service

_bearer = security.HTTPBearer(auto_error=False)


def get_runtime(request: fastapi.Request) -> service.ServiceRuntime:
    """Returns the runtime of the app handling the request.

    Args:
        request: The incoming request.

    Returns:
        The service runtime.
    """
    return request.app.state.runtime


def get_settings(request: fastapi.Request) -> config.ServiceSettings:
    """Returns the settings of the app handling the request.

    Args:
        request: The incoming request.

    Returns:
        The service settings.
    """
    return get_runtime(request).settings


async def get_session(
    request: fastapi.Request,
) -> AsyncIterator[sa_asyncio.AsyncSession]:
    """Opens one database session per request.

    Args:
        request: The incoming request.

    Yields:
        A session that is closed when the request finishes.
    """
    async with get_runtime(request).db.sessionmaker() as session:
        yield session


async def get_current_user(
    request: fastapi.Request,
    credentials: Annotated[
        security.HTTPAuthorizationCredentials | None, fastapi.Depends(_bearer)
    ],
) -> auth.CurrentUser:
    """Authenticates the caller from their bearer token.

    Args:
        request: The incoming request.
        credentials: The parsed ``Authorization`` header, if any.

    Returns:
        The authenticated user.

    Raises:
        errors.AuthenticationError: No token or an invalid token was sent.
    """
    if credentials is None:
        raise errors.AuthenticationError("Sign in to continue.")
    return auth.decode_access_token(
        get_settings(request), credentials.credentials
    )


async def get_ops_user(
    user: Annotated[auth.CurrentUser, fastapi.Depends(get_current_user)],
) -> auth.CurrentUser:
    """Authenticates the caller and requires an ops role.

    Args:
        user: The authenticated user.

    Returns:
        The same user.

    Raises:
        errors.PermissionDeniedError: The user is not an ops user.
    """
    auth.require_ops(user)
    return user


Session = Annotated[sa_asyncio.AsyncSession, fastapi.Depends(get_session)]
CurrentUser = Annotated[auth.CurrentUser, fastapi.Depends(get_current_user)]
OpsUser = Annotated[auth.CurrentUser, fastapi.Depends(get_ops_user)]
