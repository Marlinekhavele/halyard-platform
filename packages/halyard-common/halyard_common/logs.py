"""Structured logging, request logging and correlation ids.

Every log record carries a correlation id: the ``X-Request-ID`` of the HTTP
request being handled, or the id carried by the event being consumed. Events
staged while handling a request inherit it, so one booking can be followed
through Commercial, Operations, Billing and Notifications.

Set ``LOG_JSON=true`` for one JSON object per line (for log aggregation) and
``LOG_LEVEL`` for the minimum level.
"""

import contextvars
import datetime
import json
import logging
import re
import time
from typing import Any
import uuid

# The id that ties together everything done for one request or event.
correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

REQUEST_ID_HEADER = "x-request-id"
# Accept ids from the gateway only if they are short and harmless in logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
# Attributes every LogRecord has; anything else was passed via ``extra=``.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "correlation_id", "service"}
_HANDLER_NAME = "halyard"
_QUIET_LOGGERS = {
    # Requests are logged by RequestLoggingMiddleware instead.
    "uvicorn.access": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
    "aio_pika": logging.WARNING,
    "aiormq": logging.WARNING,
}


def new_id() -> str:
    """Returns a new random correlation id."""
    return uuid.uuid4().hex


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_ATTRS and not key.startswith("_")
    }


class ContextFilter(logging.Filter):
    """Adds the service name and current correlation id to every record."""

    def __init__(self, service: str) -> None:
        """Initialises the filter.

        Args:
            service: Name reported in every record.
        """
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        """Annotates the record; never drops it."""
        record.service = self._service
        record.correlation_id = correlation_id.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Formats each record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Returns the record as a JSON string."""
        entry = {
            "time": datetime.datetime.fromtimestamp(
                record.created, datetime.UTC
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": getattr(record, "service", None),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
            "message": record.getMessage(),
            **_extras(record),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable format for local development, extras as key=value."""

    def __init__(self) -> None:
        """Initialises the formatter."""
        super().__init__(
            "%(asctime)s %(levelname)-7s %(name)s [%(correlation_id)s]"
            " %(message)s"
        )

    def format(self, record: logging.LogRecord) -> str:
        """Returns the record as one readable line (plus any traceback)."""
        line = super().format(record)
        extras = " ".join(f"{k}={v}" for k, v in _extras(record).items())
        if not extras:
            return line
        first, _, rest = line.partition("\n")
        return f"{first} {extras}" + (f"\n{rest}" if rest else "")


def configure_logging(
    level: str = "INFO", json_output: bool = False, service: str = "halyard"
) -> None:
    """Installs Halyard's log handler on the root logger.

    Safe to call more than once: the previous Halyard handler is replaced.

    Args:
        level: Minimum level name, for example ``"INFO"``.
        json_output: One JSON object per line instead of readable text.
        service: Service name added to every record.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(ContextFilter(service))
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name, quiet_level in _QUIET_LOGGERS.items():
        logging.getLogger(name).setLevel(quiet_level)


class RequestLoggingMiddleware:
    """ASGI middleware that logs every request and sets its correlation id.

    Uses an ``X-Request-ID`` from the caller (for example the gateway) if it
    is valid, otherwise generates one, and returns it in the response.
    Unhandled exceptions are logged with their traceback and re-raised.
    """

    def __init__(self, app: Any, skip_paths: tuple[str, ...] = ("/health",)):
        """Wraps an ASGI app.

        Args:
            app: The wrapped ASGI application.
            skip_paths: Paths not worth a log line, such as health checks.
        """
        self.app = app
        self.skip_paths = skip_paths
        self.log = logging.getLogger("halyard.http")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """Handles one ASGI call."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.encode(), b"").decode(
            "latin-1"
        )
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else new_id()
        token = correlation_id.set(request_id)
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: dict) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (REQUEST_ID_HEADER.encode(), request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            self.log.exception(
                "unhandled error",
                extra={"method": scope["method"], "path": scope["path"]},
            )
            raise
        finally:
            if scope["path"] not in self.skip_paths:
                self.log.log(
                    logging.ERROR if status >= 500 else logging.INFO,
                    "%s %s %s",
                    scope["method"],
                    scope["path"],
                    status,
                    extra={
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 1
                        ),
                    },
                )
            correlation_id.reset(token)
