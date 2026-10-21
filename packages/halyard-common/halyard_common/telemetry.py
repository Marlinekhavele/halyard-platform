"""Optional OpenTelemetry tracing.

Active only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set and the ``telemetry``
extra is installed. Traces follow one request across all services, for
example in Jaeger.
"""

# pylint: disable=import-outside-toplevel
import logging
from typing import Any

_log = logging.getLogger("halyard.telemetry")


def setup_telemetry(
    app: Any, service_name: str, endpoint: str | None, engine: Any = None
) -> None:
    """Instruments the app (and optionally the database engine) for tracing.

    Args:
        app: The FastAPI application.
        service_name: Reported as ``service.name``.
        endpoint: OTLP HTTP endpoint. Tracing is disabled when empty.
        engine: SQLAlchemy async engine to instrument, if any.
    """
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http import trace_exporter
        from opentelemetry.instrumentation import fastapi as otel_fastapi
        from opentelemetry.sdk import resources
        from opentelemetry.sdk import trace as sdk_trace
        from opentelemetry.sdk.trace import export
    except ImportError:
        _log.warning(
            "OTEL endpoint set but opentelemetry packages are not installed;"
            " tracing disabled"
        )
        return

    provider = sdk_trace.TracerProvider(
        resource=resources.Resource.create({"service.name": service_name})
    )
    exporter = trace_exporter.OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces"
    )
    provider.add_span_processor(export.BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    otel_fastapi.FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    if engine is not None:
        try:
            from opentelemetry.instrumentation import sqlalchemy as otel_sa

            otel_sa.SQLAlchemyInstrumentor().instrument(
                engine=engine.sync_engine
            )
        except ImportError:
            pass
    _log.info("tracing enabled for %s -> %s", service_name, endpoint)
