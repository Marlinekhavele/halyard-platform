"""HTTP and event-consumer tests for the Billing service."""

import pytest

from halyard_common import bus
from halyard_common import events
from halyard_common import testing

from .. import conftest


@pytest.fixture(name="customer")
def fixture_customer(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.customer_user())


@pytest.fixture(name="ops")
def fixture_ops(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.ops_user())


async def _publish(event_type: str, payload) -> None:
    await bus.InMemoryBus().publish(
        events.EventEnvelope(
            type=event_type,
            source="test",
            data=payload.model_dump(mode="json"),
        )
    )


async def test_events_drive_the_invoice_lifecycle(client, customer, ops):
    await _publish(
        events.EventType.BOOKING_CONFIRMED, conftest.booking_confirmed()
    )

    assert (await client.get("/invoices", headers=customer)).json() == []
    [draft] = (await client.get("/invoices", headers=ops)).json()
    assert draft["status"] == "draft"
    assert draft["gross_profit_cents"] == 20_000

    await _publish(events.EventType.MILESTONE_REACHED, conftest.departed())

    [issued] = (await client.get("/invoices", headers=customer)).json()
    assert issued["id"] == draft["id"]
    assert issued["number"].startswith("INV-")
    assert issued["status"] == "issued"
    assert issued["cost_cents"] is None
    assert issued["gross_profit_cents"] is None
    assert all(line["cost_cents"] is None for line in issued["lines"])
    assert not bus.InMemoryBus.dead_letters


async def test_mark_paid_and_margin_report(client, customer, ops):
    await _publish(
        events.EventType.BOOKING_CONFIRMED, conftest.booking_confirmed()
    )
    await _publish(events.EventType.MILESTONE_REACHED, conftest.departed())
    [invoice] = (await client.get("/invoices", headers=ops)).json()
    url = f"/invoices/{invoice['id']}/mark-paid"

    assert (await client.post(url, headers=customer)).status_code == 403
    r = await client.post(url, headers=ops)
    assert r.json()["status"] == "paid"
    assert (await client.post(url, headers=ops)).status_code == 409

    report = (await client.get("/reports/margin", headers=ops)).json()
    assert report["totals"]["teu"] == 4
    r = await client.get("/reports/margin", headers=customer)
    assert r.status_code == 403


async def test_unknown_invoice_is_404(client, ops):
    r = await client.get("/invoices/missing", headers=ops)

    assert r.status_code == 404
    assert r.json()["detail"] == "Invoice not found."
