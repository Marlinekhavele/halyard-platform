"""Domain errors raised by the service layer and their HTTP mapping.

Services and repositories never raise ``fastapi.HTTPException``. They raise
one of the errors below, and ``install_error_handlers`` turns it into a JSON
response of the form ``{"detail": "<message>"}`` with the matching status code.
Keeping HTTP out of the business logic lets the same services run behind the
API and inside event consumers.
"""

import http

import fastapi
from fastapi import responses


class ServiceError(Exception):
    """Base class for expected, user-facing failures.

    Attributes:
        message: Human-readable explanation, safe to show to the caller.
        status_code: HTTP status the API layer responds with.
    """

    status_code: int = http.HTTPStatus.BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(ServiceError):
    """The caller is not signed in or their credentials are invalid."""

    status_code = http.HTTPStatus.UNAUTHORIZED


class PermissionDeniedError(ServiceError):
    """The caller is signed in but may not perform this action."""

    status_code = http.HTTPStatus.FORBIDDEN


class NotFoundError(ServiceError):
    """The requested resource does not exist or is not visible to the caller."""

    status_code = http.HTTPStatus.NOT_FOUND


class ConflictError(ServiceError):
    """The action clashes with the current state of the resource."""

    status_code = http.HTTPStatus.CONFLICT


class PayloadTooLargeError(ServiceError):
    """The uploaded payload exceeds the allowed size."""

    status_code = http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class UnsupportedMediaTypeError(ServiceError):
    """The uploaded payload has a content type we do not accept."""

    status_code = http.HTTPStatus.UNSUPPORTED_MEDIA_TYPE


class InvalidRequestError(ServiceError):
    """The request is well-formed but violates a business rule."""

    status_code = http.HTTPStatus.UNPROCESSABLE_ENTITY


async def _handle_service_error(
    request: fastapi.Request, exc: Exception
) -> responses.JSONResponse:
    """Converts a ``ServiceError`` into a JSON error response.

    Args:
        request: The request that failed. Unused, required by Starlette.
        exc: The raised error.

    Returns:
        A JSON response carrying the error message and status code.
    """
    del request  # Unused.
    assert isinstance(exc, ServiceError)
    return responses.JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}
    )


def install_error_handlers(app: fastapi.FastAPI) -> None:
    """Registers the ``ServiceError`` handler on a FastAPI app.

    Args:
        app: The application to configure.
    """
    app.add_exception_handler(ServiceError, _handle_service_error)
