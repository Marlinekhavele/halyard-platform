"""HTTP tests for the Commercial API."""

import datetime

import pytest

from halyard_common import testing

QUOTE = {
    "pol": "CNSHA",
    "pod": "DEHAM",
    "container_type": "40HC",
    "quantity": 1,
    "ready_date": str(datetime.date.today() + datetime.timedelta(days=5)),
}


@pytest.fixture(name="customer")
def fixture_customer(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.customer_user())


@pytest.fixture(name="ops")
def fixture_ops(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.ops_user())


async def test_ports_are_public(client):
    r = await client.get("/ports")

    assert r.status_code == 200
    assert "DEHAM" in [p["code"] for p in r.json()]


async def test_estimate_is_public_and_hides_costs(client):
    r = await client.post("/quotes/estimate", json=QUOTE)

    assert r.status_code == 200
    options = r.json()["options"]
    assert len(options) == 3
    assert all(o["id"] is None for o in options)
    assert all(o["total_cost_cents"] is None for o in options)


async def test_same_ports_are_rejected(client):
    r = await client.post("/quotes/estimate", json={**QUOTE, "pod": "CNSHA"})

    assert r.status_code == 422


async def test_unknown_port_is_422_with_detail(client):
    r = await client.post("/quotes/estimate", json={**QUOTE, "pol": "ZZZZZ"})

    assert r.status_code == 422
    assert r.json()["detail"] == "We don't serve port ZZZZZ yet."


async def test_quotes_require_sign_in(client):
    assert (await client.post("/quotes", json=QUOTE)).status_code == 401


async def test_costs_are_only_shown_to_ops(client, customer, ops):
    r = await client.post("/quotes", json=QUOTE, headers=customer)
    assert r.status_code == 201
    quote = r.json()
    assert quote["options"][0]["total_cost_cents"] is None

    r = await client.get(f"/quotes/{quote['id']}", headers=ops)
    assert r.json()["options"][0]["total_cost_cents"] > 0


async def test_booking_flow(client, customer, ops):
    quote = (await client.post("/quotes", json=QUOTE, headers=customer)).json()
    option_id = quote["options"][0]["id"]

    r = await client.post(
        f"/quotes/{quote['id']}/options/{option_id}/book",
        json={"gross_weight_kg": 12_000},
        headers=customer,
    )
    assert r.status_code == 201
    booking = r.json()

    r = await client.post(
        f"/bookings/{booking['id']}/confirm",
        json={"vessel": "Elbe Meridian", "voyage": "052W"},
        headers=customer,
    )
    assert r.status_code == 403

    r = await client.post(
        f"/bookings/{booking['id']}/confirm",
        json={"vessel": "Elbe Meridian", "voyage": "052W"},
        headers=ops,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

    r = await client.get("/bookings?status=confirmed", headers=customer)
    assert [b["ref"] for b in r.json()] == [booking["ref"]]


async def test_confirm_validates_schedule(client, ops):
    r = await client.post(
        "/bookings/any/confirm",
        json={
            "vessel": "Elbe",
            "voyage": "052W",
            "etd": "2026-10-10",
            "eta": "2026-10-01",
        },
        headers=ops,
    )

    assert r.status_code == 422


async def test_rates_and_leads_are_ops_only(client, customer, ops):
    for path in ("/rates", "/surcharges", "/leads", "/vessels?carrier=MSC"):
        assert (await client.get(path, headers=customer)).status_code == 403
        assert (await client.get(path, headers=ops)).status_code == 200


async def test_lead_submission(client, ops):
    r = await client.post(
        "/leads",
        json={"name": "Max", "company": "Weber", "email": "max@w.example"},
    )
    assert r.status_code == 201
    assert r.json() == {"status": "received"}

    [lead] = (await client.get("/leads", headers=ops)).json()
    r = await client.patch(
        f"/leads/{lead['id']}", json={"status": "won"}, headers=ops
    )
    assert r.json()["status"] == "won"
