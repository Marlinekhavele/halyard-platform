"""Tests for operations.services."""

import datetime

import pytest
import sqlalchemy as sa

from halyard_common import errors
from halyard_common import events
from halyard_common import testing
from operations import models
from operations import schemas
from operations import services
from operations.domain import shipping

from .. import conftest

CUSTOMER = testing.customer_user()
OTHER_CUSTOMER = testing.customer_user(testing.OTHER_COMPANY_ID)
OPS = testing.ops_user()
PDF = b"%PDF-1.4\n"
UTC = datetime.UTC


async def _staged_types(session) -> list[str]:
    rows = await session.scalars(
        sa.select(models.OutboxEvent.type).order_by(
            models.OutboxEvent.created_at
        )
    )
    return list(rows)


@pytest.fixture(name="shipment")
async def fixture_shipment(make_service, session) -> models.Shipment:
    shipment = await make_service(services.ShipmentService).open_for_booking(
        conftest.booking_confirmed()
    )
    await session.commit()
    return shipment


@pytest.fixture(name="tracking")
def fixture_tracking(make_service) -> services.TrackingService:
    return make_service(services.TrackingService)


@pytest.fixture(name="documents")
def fixture_documents(make_service) -> services.DocumentService:
    return make_service(services.DocumentService)


def _event(container: str, event: str, day: datetime.date, **extra):
    return schemas.TrackingWebhook(
        container_number=container,
        event=event,
        occurred_at=datetime.datetime.combine(
            day, datetime.time(10), tzinfo=UTC
        ),
        **extra,
    )


def _doc(shipment: models.Shipment, doc_type: str) -> models.Document:
    return next(d for d in shipment.documents if d.doc_type == doc_type)


# ---- Opening shipments -----------------------------------------------------


async def test_open_for_booking_builds_the_shipment(shipment, session):
    assert shipment.ref == "HLY-26-00001"
    assert shipment.status == "booked"
    assert shipment.planned_eta == conftest.ETA
    assert len(shipment.containers) == 2
    assert shipment.milestones[0].code == "BOOKED"
    assert shipment.milestones[0].actual_at is not None
    assert all(m.actual_at is None for m in shipment.milestones[1:])
    assert "TRANSSHIPMENT" in [m.code for m in shipment.milestones]
    assert len(shipment.documents) == 5
    assert await _staged_types(session) == [events.EventType.SHIPMENT_CREATED]


async def test_open_for_booking_is_idempotent(shipment, make_service):
    again = await make_service(services.ShipmentService).open_for_booking(
        conftest.booking_confirmed()
    )

    assert again is None


async def test_cancel_only_affects_shipments_not_yet_moving(
    shipment, make_service, session
):
    shipments = make_service(services.ShipmentService)

    await shipments.cancel_for_booking(shipment.booking_id)
    assert shipment.status == "cancelled"

    shipment.status = "in_transit"
    await shipments.cancel_for_booking(shipment.booking_id)
    assert shipment.status == "in_transit"


async def test_visibility(shipment, make_service):
    shipments = make_service(services.ShipmentService)

    by_ref = await shipments.get_visible_shipment(CUSTOMER, shipment.ref)
    assert by_ref.id == shipment.id
    assert await shipments.get_visible_shipment(OPS, shipment.id)
    with pytest.raises(errors.NotFoundError):
        await shipments.get_visible_shipment(OTHER_CUSTOMER, shipment.ref)
    assert await shipments.list_shipments(OTHER_CUSTOMER) == []


async def test_list_filters(shipment, make_service):
    shipments = make_service(services.ShipmentService)
    number = shipment.containers[0].number

    assert len(await shipments.list_shipments(CUSTOMER, "active")) == 1
    assert await shipments.list_shipments(CUSTOMER, "delivered") == []
    assert len(await shipments.list_shipments(CUSTOMER, query="elbe")) == 1
    assert len(await shipments.list_shipments(CUSTOMER, query=number)) == 1
    assert await shipments.list_shipments(CUSTOMER, query="nothing") == []
    # Documents are open, so the shipment needs action.
    assert await shipments.list_shipments(CUSTOMER, needs_action=False) == []


async def test_stats(shipment, make_service):
    stats = await make_service(services.ShipmentService).stats(OPS)

    assert stats.active == 1
    assert stats.active_teu == 4
    assert stats.needs_action == 1
    assert stats.delivered == 0


# ---- Tracking --------------------------------------------------------------


async def test_webhook_checks_token_and_container(shipment, tracking):
    number = shipment.containers[0].number

    with pytest.raises(errors.AuthenticationError):
        await tracking.receive_webhook(
            "wrong", _event(number, "GATE_IN", conftest.ETD)
        )
    with pytest.raises(errors.NotFoundError):
        await tracking.receive_webhook(
            "secret-token", _event("MSKU9070323", "GATE_IN", conftest.ETD)
        )


async def test_webhook_normalises_container_number(shipment, tracking):
    number = shipment.containers[0].number
    spaced = f"{number[:4]} {number[4:10]} {number[10]}".lower()

    outcome = await tracking.receive_webhook(
        "secret-token", _event(spaced, "GATE_IN", conftest.ETD)
    )

    assert outcome.applied == "gate_in recorded"


async def test_unknown_event_is_rejected(shipment, tracking):
    with pytest.raises(errors.InvalidRequestError, match="Unknown"):
        tracking.apply(
            shipment,
            shipment.containers[0],
            _event(shipment.containers[0].number, "TELEPORTED", conftest.ETD),
        )


async def test_departure_backfills_and_issues_bill_of_lading(
    shipment, tracking, session
):
    container = shipment.containers[0]

    applied = tracking.apply(
        shipment, container, _event(container.number, "DEPARTED", conftest.ETD)
    )

    assert applied == "departed recorded"
    assert shipment.status == "in_transit"
    assert shipment.bill_of_lading
    reached = [m.code for m in shipment.milestones if m.actual_at]
    assert reached == [
        "BOOKED",
        "EMPTY_PICKUP",
        "GATE_IN",
        "LOADED",
        "DEPARTED",
    ]
    assert container.last_event == "DEPARTED"
    await session.flush()
    assert events.EventType.MILESTONE_REACHED in await _staged_types(session)


async def test_repeated_milestone_is_ignored(shipment, tracking):
    container = shipment.containers[0]
    departed = _event(container.number, "DEPARTED", conftest.ETD)

    tracking.apply(shipment, container, departed)

    assert tracking.apply(shipment, container, departed) == "already recorded"


async def test_eta_change_moves_arrival_milestones(shipment, tracking, session):
    container = shipment.containers[0]
    new_eta = conftest.ETA + datetime.timedelta(days=3)
    arrived = next(m for m in shipment.milestones if m.code == "ARRIVED")

    applied = tracking.apply(
        shipment,
        container,
        _event(
            container.number,
            "ETA_CHANGED",
            conftest.ETD,
            new_eta=new_eta,
            reason="Congestion",
        ),
    )

    assert applied == "eta moved +3 days"
    assert shipment.eta == new_eta
    assert shipment.delay_reason == "Congestion"
    assert arrived.planned_at == new_eta
    await session.flush()
    assert events.EventType.SHIPMENT_DELAYED in await _staged_types(session)


async def test_eta_change_needs_new_eta(shipment, tracking):
    container = shipment.containers[0]

    with pytest.raises(errors.InvalidRequestError, match="new_eta"):
        tracking.apply(
            shipment,
            container,
            _event(container.number, "ETA_CHANGED", conftest.ETD),
        )


async def test_customs_hold_and_release(shipment, tracking):
    container = shipment.containers[0]

    tracking.apply(
        shipment,
        container,
        _event(container.number, "CUSTOMS_HOLD", conftest.ETA),
    )
    assert shipment.status == "customs_hold"
    assert shipment.hold_reason == "Held by customs for inspection."

    tracking.apply(
        shipment,
        container,
        _event(container.number, "CUSTOMS_RELEASED", conftest.ETA),
    )
    assert shipment.status == "at_port"
    assert shipment.hold_reason is None


async def test_delivery_waits_for_every_container(shipment, tracking):
    first, second = shipment.containers
    day = conftest.ETA + datetime.timedelta(days=4)

    waiting = tracking.apply(
        shipment, first, _event(first.number, "DELIVERED", day)
    )
    done = tracking.apply(
        shipment, second, _event(second.number, "DELIVERED", day)
    )

    assert waiting == "container delivered; waiting for the others"
    assert done == "delivered recorded"
    assert shipment.status == "delivered"
    assert shipment.delivered_at is not None
    ignored = tracking.apply(
        shipment, first, _event(first.number, "ARRIVED", day)
    )
    assert ignored == "ignored: shipment is delivered"


async def test_simulate_walks_to_delivery(shipment, tracking):
    for _ in range(len(shipment.milestones) - 1):
        await tracking.simulate(OPS, shipment.ref, schemas.SimulateStep())

    assert shipment.status == "delivered"
    with pytest.raises(errors.ConflictError, match="every milestone"):
        await tracking.simulate(OPS, shipment.ref, schemas.SimulateStep())
    with pytest.raises(errors.PermissionDeniedError):
        await tracking.simulate(CUSTOMER, shipment.ref, schemas.SimulateStep())


# ---- Documents -------------------------------------------------------------


async def test_customer_upload_then_ops_review(shipment, documents, session):
    doc = _doc(shipment, "COMMERCIAL_INVOICE")

    uploaded, ref = await documents.upload(
        CUSTOMER, doc.id, "invoice.pdf", "application/pdf", PDF
    )
    assert ref == shipment.ref
    assert uploaded.status == "uploaded"
    assert uploaded.uploaded_at == conftest.NOW

    with pytest.raises(errors.PermissionDeniedError):
        await documents.review(CUSTOMER, doc.id, True, None)
    with pytest.raises(errors.InvalidRequestError):
        await documents.review(OPS, doc.id, False, None)

    rejected, _ = await documents.review(OPS, doc.id, False, "Missing EORI")
    assert rejected.status == "required"
    assert rejected.note == "Missing EORI"

    await documents.upload(CUSTOMER, doc.id, "v2.pdf", "application/pdf", PDF)
    approved, _ = await documents.review(OPS, doc.id, True, None)
    assert approved.status == "approved"
    with pytest.raises(errors.ConflictError, match="already approved"):
        await documents.upload(
            CUSTOMER, doc.id, "v3.pdf", "application/pdf", PDF
        )

    types = await _staged_types(session)
    assert types.count(events.EventType.DOCUMENT_UPLOADED) == 2
    assert types.count(events.EventType.DOCUMENT_REVIEWED) == 2


async def test_ops_shares_document_for_customer_approval(shipment, documents):
    doc = _doc(shipment, "BILL_OF_LADING")

    with pytest.raises(errors.ConflictError, match="when it is ready"):
        await documents.upload(
            CUSTOMER, doc.id, "bl.pdf", "application/pdf", PDF
        )
    shared, _ = await documents.upload(
        OPS, doc.id, "bl.pdf", "application/pdf", PDF
    )
    assert shared.status == "review"
    with pytest.raises(errors.ConflictError, match="Waiting for the customer"):
        await documents.review(OPS, doc.id, True, None)

    sent_back, _ = await documents.review(CUSTOMER, doc.id, False, "Typo")
    assert sent_back.status == "not_due"


async def test_upload_replaces_previous_file(shipment, documents, file_storage):
    doc = _doc(shipment, "PACKING_LIST")

    await documents.upload(CUSTOMER, doc.id, "a.pdf", "application/pdf", PDF)
    await documents.review(OPS, doc.id, False, "Wrong file")
    await documents.upload(
        CUSTOMER, doc.id, "b.pdf", "application/pdf", PDF + b"v2"
    )

    assert list(file_storage.files.values()) == [PDF + b"v2"]
    downloaded = await documents.download(CUSTOMER, doc.id)
    assert downloaded.data == PDF + b"v2"
    assert downloaded.filename == "b.pdf"


async def test_upload_limits(shipment, documents, monkeypatch):
    doc = _doc(shipment, "PACKING_LIST")

    with pytest.raises(errors.UnsupportedMediaTypeError):
        await documents.upload(CUSTOMER, doc.id, "x.exe", None, b"MZ")
    monkeypatch.setattr(shipping, "MAX_UPLOAD_BYTES", 3)
    with pytest.raises(errors.PayloadTooLargeError):
        await documents.upload(
            CUSTOMER, doc.id, "big.pdf", "application/pdf", PDF
        )


async def test_documents_are_scoped(shipment, documents):
    doc = _doc(shipment, "PACKING_LIST")

    with pytest.raises(errors.NotFoundError):
        await documents.get_document(OTHER_CUSTOMER, doc.id)
    with pytest.raises(errors.NotFoundError, match="No file"):
        await documents.download(CUSTOMER, doc.id)
    assert await documents.list_documents(OTHER_CUSTOMER, None) == []


async def test_open_documents_differ_for_ops_and_customers(shipment, documents):
    doc = _doc(shipment, "PACKING_LIST")
    await documents.upload(CUSTOMER, doc.id, "p.pdf", "application/pdf", PDF)

    ops_open = await documents.list_documents(OPS, "open")
    customer_open = await documents.list_documents(CUSTOMER, "open")

    assert [d.doc_type for d, _ in ops_open] == ["PACKING_LIST"]
    assert "PACKING_LIST" not in [d.doc_type for d, _ in customer_open]
    assert len(customer_open) == 3
    assert all(ref == shipment.ref for _, ref in customer_open)
