"""HTTP and event-consumer tests for the Operations service."""

import pytest

from halyard_common import bus
from halyard_common import events
from halyard_common import testing

from .. import conftest

PDF = b"%PDF-1.4\n"


@pytest.fixture(name="customer")
def fixture_customer(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.customer_user())


@pytest.fixture(name="ops")
def fixture_ops(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.ops_user())


async def _publish(event_type: str, payload) -> events.EventEnvelope:
    envelope = events.EventEnvelope(
        type=event_type,
        source="commercial",
        data=payload.model_dump(mode="json"),
    )
    await bus.InMemoryBus().publish(envelope)
    return envelope


@pytest.fixture(name="shipment")
async def fixture_shipment(client, customer):
    await _publish(
        events.EventType.BOOKING_CONFIRMED, conftest.booking_confirmed()
    )
    r = await client.get("/shipments/HLY-26-00001", headers=customer)
    assert r.status_code == 200, r.text
    return r.json()


async def test_booking_confirmed_event_opens_shipment(shipment):
    assert shipment["pol_name"] == "Shanghai"
    assert shipment["container_count"] == 2
    assert shipment["needs_action"] is True
    assert not bus.InMemoryBus.dead_letters


async def test_redelivered_event_is_ignored(client, customer):
    envelope = await _publish(
        events.EventType.BOOKING_CONFIRMED, conftest.booking_confirmed()
    )

    await bus.InMemoryBus().publish(envelope)

    r = await client.get("/shipments", headers=customer)
    assert len(r.json()) == 1
    assert not bus.InMemoryBus.dead_letters


async def test_booking_cancelled_event_cancels_shipment(
    client, customer, shipment
):
    await _publish(
        events.EventType.BOOKING_CANCELLED,
        events.BookingCancelled(
            booking_id="booking-1",
            booking_ref=shipment["ref"],
            company_id=shipment["company_id"],
        ),
    )

    r = await client.get(f"/shipments/{shipment['ref']}", headers=customer)
    assert r.json()["status"] == "cancelled"


async def test_webhook(client, shipment):
    body = {
        "container_number": shipment["containers"][0]["number"],
        "event": "GATE_IN",
        "occurred_at": "2026-10-07T09:00:00Z",
    }

    r = await client.post(
        "/tracking/webhook", json=body, headers={"X-Tracking-Token": "nope"}
    )
    assert r.status_code == 401

    r = await client.post(
        "/tracking/webhook",
        json=body,
        headers={"X-Tracking-Token": "secret-token"},
    )
    assert r.json() == {
        "shipment_ref": shipment["ref"],
        "status": "booked",
        "applied": "gate_in recorded",
    }


async def test_simulate_is_ops_only(client, shipment, customer, ops):
    url = f"/shipments/{shipment['ref']}/simulate"

    assert (await client.post(url, json={}, headers=customer)).status_code == (
        403
    )
    r = await client.post(url, json={"event": "DEPARTED"}, headers=ops)
    assert r.json()["status"] == "in_transit"


async def test_other_company_sees_nothing(client, shipment, settings):
    other = testing.auth_headers(
        settings, testing.customer_user(testing.OTHER_COMPANY_ID)
    )

    r = await client.get(f"/shipments/{shipment['ref']}", headers=other)
    assert r.status_code == 404
    assert (await client.get("/shipments", headers=other)).json() == []


async def test_document_upload_and_download(client, shipment, customer, ops):
    doc = shipment["documents"][0]

    r = await client.post(
        f"/documents/{doc['id']}/upload",
        files={"file": ("invoice.pdf", PDF, "application/pdf")},
        headers=customer,
    )
    assert r.status_code == 200
    assert r.json()["shipment_ref"] == shipment["ref"]

    r = await client.get("/documents?status=open", headers=ops)
    assert [d["id"] for d in r.json()] == [doc["id"]]

    r = await client.get(f"/documents/{doc['id']}/file", headers=customer)
    assert r.content == PDF
    assert "invoice.pdf" in r.headers["content-disposition"]


async def test_upload_rejects_unsupported_type(client, shipment, customer):
    doc = shipment["documents"][0]

    r = await client.post(
        f"/documents/{doc['id']}/upload",
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
        headers=customer,
    )

    assert r.status_code == 415


async def test_stats(client, shipment, ops):
    r = await client.get("/stats", headers=ops)

    assert r.json()["active"] == 1
    assert r.json()["documents_to_check"] == 0
