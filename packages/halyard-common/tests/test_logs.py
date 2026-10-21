"""Tests for halyard_common.logs and correlation through events."""

import json
import logging
import sys

import fastapi
import pytest

from halyard_common import bus
from halyard_common import config
from halyard_common import db
from halyard_common import events
from halyard_common import logs
from halyard_common import outbox
from halyard_common import service
from halyard_common import testing

Base = db.make_base()


class OutboxEvent(outbox.OutboxMixin, Base):
    """Toy outbox table."""

    __tablename__ = "outbox"


class ProcessedEvent(outbox.ProcessedEventMixin, Base):
    """Toy inbox table."""

    __tablename__ = "processed_events"


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        "halyard.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
    )
    record.__dict__.update(extra)
    logs.ContextFilter("billing").filter(record)
    return record


# ---- Formatting ------------------------------------------------------------


def test_json_formatter_writes_one_object_with_context_and_extras():
    token = logs.correlation_id.set("req-1")
    try:
        line = logs.JsonFormatter().format(_record(invoice_id="i1"))
    finally:
        logs.correlation_id.reset(token)

    entry = json.loads(line)
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["service"] == "billing"
    assert entry["correlation_id"] == "req-1"
    assert entry["invoice_id"] == "i1"
    assert entry["time"].endswith("+00:00")


def test_json_formatter_includes_the_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record()
        record.exc_info = sys.exc_info()

    entry = json.loads(logs.JsonFormatter().format(record))

    assert "ValueError: boom" in entry["exception"]


def test_text_formatter_appends_extras():
    line = logs.TextFormatter().format(_record(status=201))

    assert "halyard.test [-] hello world status=201" in line


def test_configure_logging_replaces_its_own_handler():
    root = logging.getLogger()
    before = len(root.handlers)

    logs.configure_logging("DEBUG", json_output=True, service="x")
    logs.configure_logging("INFO", json_output=False, service="y")

    ours = [h for h in root.handlers if h.get_name() == "halyard"]
    assert len(ours) == 1
    assert len(root.handlers) <= before + 1
    assert root.level == logging.INFO
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


# ---- Request logging -------------------------------------------------------

router = fastapi.APIRouter()


@router.get("/ok")
async def ok() -> dict:
    return {"correlation_id": logs.correlation_id.get()}


@router.get("/boom")
async def boom() -> dict:
    raise RuntimeError("unexpected")


@pytest.fixture(name="client")
async def fixture_client(tmp_path):
    settings = config.ServiceSettings(
        service_name="probe", database_url=testing.sqlite_url(tmp_path)
    )
    runtime = service.ServiceRuntime(settings, db.make_base().metadata)
    app = service.create_app(runtime, "Probe", "Test app", [router])
    async with testing.running_client(app) as client:
        yield client


async def test_request_gets_an_id_and_a_log_line(client, caplog):
    caplog.set_level(logging.INFO, logger="halyard.http")

    r = await client.get("/ok")

    request_id = r.headers["x-request-id"]
    assert len(request_id) == 32
    assert r.json() == {"correlation_id": request_id}
    [line] = [rec for rec in caplog.records if rec.name == "halyard.http"]
    assert (line.method, line.path, line.status) == ("GET", "/ok", 200)
    assert line.duration_ms >= 0


async def test_valid_incoming_request_id_is_kept(client):
    r = await client.get("/ok", headers={"X-Request-ID": "gw-123"})

    assert r.headers["x-request-id"] == "gw-123"


async def test_unsafe_incoming_request_id_is_replaced(client):
    r = await client.get("/ok", headers={"X-Request-ID": "bad id\twith space"})

    assert r.headers["x-request-id"] != "bad id\twith space"


async def test_health_checks_are_not_logged(client, caplog):
    caplog.set_level(logging.INFO, logger="halyard.http")

    await client.get("/health")

    assert not [rec for rec in caplog.records if rec.name == "halyard.http"]


async def test_unhandled_errors_are_logged_with_traceback(client, caplog):
    caplog.set_level(logging.INFO, logger="halyard.http")

    with pytest.raises(RuntimeError):
        await client.get("/boom")

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(r.exc_info for r in errors)
    assert any(getattr(r, "status", None) == 500 for r in errors)


# ---- Correlation through events --------------------------------------------


async def test_events_carry_and_restore_the_correlation_id(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="halyard.outbox")
    database = db.Database(testing.sqlite_url(tmp_path))
    await database.create_all(Base.metadata)
    seen: list[str | None] = []

    async def handler(session, envelope):
        seen.append(logs.correlation_id.get())

    consume = outbox.idempotent_consumer(
        database, ProcessedEvent, {"x.y": handler}
    )
    bus.InMemoryBus.reset()
    await bus.InMemoryBus().subscribe("svc.events", ["x.y"], consume)

    token = logs.correlation_id.set("req-42")
    try:
        async with database.sessionmaker() as session:
            staged = outbox.OutboxRepository(session, OutboxEvent, "svc").add(
                "x.y", {}
            )
            await session.commit()
    finally:
        logs.correlation_id.reset(token)
    await outbox.OutboxRelay(database, OutboxEvent, bus.InMemoryBus()).flush()

    assert staged.correlation_id == "req-42"
    assert seen == ["req-42"]
    assert logs.correlation_id.get() is None  # Restored after handling.
    messages = [r.getMessage() for r in caplog.records]
    assert "event staged x.y" in messages
    assert "event handled x.y" in messages
    bus.InMemoryBus.reset()
    await database.dispose()


def test_envelopes_without_correlation_id_stay_valid():
    envelope = events.EventEnvelope.model_validate(
        {"type": "x.y", "source": "old", "data": {}}
    )

    assert envelope.correlation_id is None
