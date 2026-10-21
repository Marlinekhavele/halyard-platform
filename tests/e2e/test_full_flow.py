"""End to end: every service in one process, talking over the in-memory bus.

Covers the whole life of a shipment: sign-in, quote, booking, ops
confirmation, shipment creation, documents, tracking, delay, invoice,
delivery, notifications and the margin report.

Run with ``pytest tests/e2e``. Uses SQLite by default; set
``E2E_POSTGRES=postgresql+asyncpg://user:pass@host`` to use Postgres (one
database per service, named ``halyard_<service>``).
"""

import asyncio
import datetime
import os
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dev_server  # noqa: E402  # pylint: disable=wrong-import-position

PDF = b"%PDF-1.4\n% Halyard test invoice\n"
TRACKING_TOKEN = "dev-tracking-token"


async def eventually(check, timeout: float = 10.0, interval: float = 0.1):
    """Polls until the other services have caught up with an event.

    Args:
        check: Coroutine function returning a truthy value when done.
        timeout: Seconds before giving up.
        interval: Seconds between polls.

    Returns:
        The first truthy value returned by ``check``.

    Raises:
        AssertionError: The condition was not met in time.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last = None
    while loop.time() < deadline:
        last = await check()
        if last:
            return last
        await asyncio.sleep(interval)
    raise AssertionError(
        f"condition not met in {timeout}s (last value: {last!r})"
    )


@pytest.fixture(name="platform")
async def fixture_platform(tmp_path, monkeypatch):
    """Starts every service in-process and yields an HTTP client."""
    # Set everything prepare_environment would, so monkeypatch undoes it.
    postgres = os.environ.get("E2E_POSTGRES")
    for name in dev_server.SERVICES:
        url = (
            f"{postgres.rstrip('/')}/halyard_{name}"
            if postgres
            else f"sqlite+aiosqlite:///{tmp_path / name}.db"
        )
        monkeypatch.setenv(f"{name.upper()}_DATABASE_URL", url)
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path / "documents"))
    monkeypatch.setenv("BROKER_URL", "memory://")
    monkeypatch.setenv("OUTBOX_POLL_SECONDS", "0.05")
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    dev_server.prepare_environment(tmp_path)

    from halyard_common import bus  # pylint: disable=import-outside-toplevel

    bus.InMemoryBus.reset()
    app = dev_server.build_app()
    runtimes = [a.state.runtime for a in app.state.services.values()]
    if postgres:  # Clean slate.
        for runtime in runtimes:
            await runtime.db.drop_all(runtime.metadata)
    await dev_server.start_all(runtimes)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client
    for runtime in runtimes:
        await runtime.stop()
    assert not bus.InMemoryBus.dead_letters, bus.InMemoryBus.dead_letters


async def login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    """Signs in and returns the ``Authorization`` header."""
    r = await client.post(
        "/api/accounts/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_quote_to_delivery(platform):
    client = platform
    customer = await login(client, "anna@nordwerk.example", "demo1234")
    ops = await login(client, "ops@halyard.example", "halyard-ops")
    today = datetime.date.today()

    # Public estimate (website) needs no sign-in.
    quote_body = {
        "pol": "CNSHA",
        "pod": "DEHAM",
        "container_type": "40HC",
        "quantity": 2,
        "ready_date": str(today + datetime.timedelta(days=5)),
        "incoterm": "FOB",
        "commodity": "Bicycle components",
        "cargo_value_cents": 8_600_000,
        "customs": True,
        "trucking": True,
        "insurance": True,
    }
    r = await client.post("/api/commercial/quotes/estimate", json=quote_body)
    assert r.status_code == 200 and len(r.json()["options"]) == 3

    # Customer requests a quote: three distinct options, no cost prices.
    r = await client.post(
        "/api/commercial/quotes", json=quote_body, headers=customer
    )
    assert r.status_code == 201, r.text
    quote = r.json()
    labels = [o["label"] for o in quote["options"]]
    assert labels == ["Best value", "Fastest", "Lowest CO₂"]
    assert all(o["total_cost_cents"] is None for o in quote["options"])
    assert all(
        line["cost_cents"] is None for line in quote["options"][0]["lines"]
    )
    option = quote["options"][0]
    book_url = (
        f"/api/commercial/quotes/{quote['id']}/options/{option['id']}/book"
    )

    # Customer books the best-value option.
    r = await client.post(
        book_url,
        json={
            "gross_weight_kg": 18400,
            "supplier_name": "Shanghai Velo Parts Co.",
        },
        headers=customer,
    )
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["status"] == "requested"
    ref = booking["ref"]

    # Ops is told about the request.
    async def ops_alerted():
        r = await client.get("/api/notifications/notifications", headers=ops)
        return next((n for n in r.json() if ref in n["title"]), None)

    alert = await eventually(ops_alerted)
    # Notifications learned about the seeded ops user and emailed them.
    assert alert["email_status"] == "logged"

    # A second booking attempt on the same quote is refused.
    r = await client.post(
        book_url, json={"gross_weight_kg": 18400}, headers=customer
    )
    assert r.status_code == 409

    # Customers cannot confirm bookings.
    confirm_url = f"/api/commercial/bookings/{booking['id']}/confirm"
    r = await client.post(
        confirm_url, json={"vessel": "X", "voyage": "1"}, headers=customer
    )
    assert r.status_code == 403

    # Ops confirms; Operations opens the shipment, Billing drafts an invoice.
    etd = today - datetime.timedelta(days=1)
    r = await client.post(
        confirm_url,
        json={"vessel": "Elbe Meridian", "voyage": "052W", "etd": str(etd)},
        headers=ops,
    )
    assert r.status_code == 200, r.text

    async def shipment_exists():
        r = await client.get(
            f"/api/operations/shipments/{ref}", headers=customer
        )
        return r.json() if r.status_code == 200 else None

    shipment = await eventually(shipment_exists)
    assert shipment["pol_name"] == "Shanghai"
    assert shipment["pod_name"] == "Hamburg"
    assert len(shipment["containers"]) == 2
    assert shipment["status"] == "booked"
    assert shipment["needs_action"] is True

    async def draft_invoice():
        r = await client.get("/api/billing/invoices", headers=ops)
        return next((i for i in r.json() if i["shipment_ref"] == ref), None)

    invoice = await eventually(draft_invoice)
    assert invoice["status"] == "draft"
    assert invoice["subtotal_cents"] == option["total_sell_cents"]
    assert invoice["gross_profit_cents"] > 0
    # Customers don't see drafts.
    r = await client.get("/api/billing/invoices", headers=customer)
    assert r.json() == []

    # Customer uploads the invoice; ops rejects, then approves a new one.
    doc = next(
        d
        for d in shipment["documents"]
        if d["doc_type"] == "COMMERCIAL_INVOICE"
    )
    doc_url = f"/api/operations/documents/{doc['id']}"
    r = await client.post(
        f"{doc_url}/upload",
        files={"file": ("invoice.pdf", PDF, "application/pdf")},
        headers=customer,
    )
    assert r.status_code == 200 and r.json()["status"] == "uploaded"
    assert all(c["ok"] for c in r.json()["checks"])
    r = await client.post(
        f"{doc_url}/review",
        json={"approve": False, "note": "EORI number missing"},
        headers=ops,
    )
    assert r.json()["status"] == "required"
    r = await client.post(
        f"{doc_url}/upload",
        files={"file": ("invoice-v2.pdf", PDF, "application/pdf")},
        headers=customer,
    )
    r = await client.post(
        f"{doc_url}/review", json={"approve": True}, headers=ops
    )
    assert r.json()["status"] == "approved"
    r = await client.get(f"{doc_url}/file", headers=customer)
    assert r.content == PDF

    # Tracking: provider webhook for container 1, then the simulator moves
    # both containers on.
    gate_in = {
        "container_number": shipment["containers"][0]["number"],
        "event": "GATE_IN",
        "occurred_at": f"{etd - datetime.timedelta(days=3)}T09:00:00Z",
        "location": "Shanghai",
    }
    r = await client.post(
        "/api/operations/tracking/webhook",
        json=gate_in,
        headers={"X-Tracking-Token": "wrong"},
    )
    assert r.status_code == 401
    r = await client.post(
        "/api/operations/tracking/webhook",
        json=gate_in,
        headers={"X-Tracking-Token": TRACKING_TOKEN},
    )
    assert r.status_code == 200 and r.json()["applied"] == "gate_in recorded"

    simulate_url = f"/api/operations/shipments/{ref}/simulate"
    r = await client.post(
        simulate_url,
        json={"event": "DEPARTED", "occurred_at": f"{etd}T18:00:00Z"},
        headers=ops,
    )
    assert r.status_code == 200 and r.json()["status"] == "in_transit"
    assert r.json()["bill_of_lading"]

    # Departure issues the invoice.
    async def issued():
        r = await client.get("/api/billing/invoices", headers=customer)
        return next((i for i in r.json() if i["status"] == "issued"), None)

    customer_invoice = await eventually(issued)
    assert customer_invoice["number"].startswith("INV-")
    assert customer_invoice["cost_cents"] is None  # Never shown to customers.

    # A 3-day delay is reported to the customer.
    new_eta = datetime.date.fromisoformat(shipment["eta"]) + datetime.timedelta(
        days=3
    )
    r = await client.post(
        simulate_url,
        json={
            "event": "ETA_CHANGED",
            "new_eta": str(new_eta),
            "reason": "Port congestion in Singapore",
        },
        headers=ops,
    )
    assert r.json()["delay_days"] == 3

    async def delay_notified():
        r = await client.get(
            "/api/notifications/notifications", headers=customer
        )
        return any("late" in n["title"] for n in r.json())

    await eventually(delay_notified)

    # Walk through the remaining milestones to delivery.
    for _ in range(10):
        r = await client.post(simulate_url, json={}, headers=ops)
        if r.status_code == 409:
            break
    final = (
        await client.get(f"/api/operations/shipments/{ref}", headers=customer)
    ).json()
    assert final["status"] == "delivered"
    assert final["progress"] == 1.0

    async def delivered_notified():
        r = await client.get(
            "/api/notifications/notifications", headers=customer
        )
        return any("delivered" in n["title"] for n in r.json())

    await eventually(delivered_notified)

    # Ops marks the invoice paid and reads the margin report.
    r = await client.post(
        f"/api/billing/invoices/{customer_invoice['id']}/mark-paid",
        headers=ops,
    )
    assert r.json()["status"] == "paid"
    report = (
        await client.get("/api/billing/reports/margin", headers=ops)
    ).json()
    assert report["totals"]["teu"] == 4
    assert report["totals"]["gross_profit_per_teu_cents"] > 0
    r = await client.get("/api/billing/reports/margin", headers=customer)
    assert r.status_code == 403

    # Another company can't see this shipment.
    r = await client.post(
        "/api/accounts/auth/register",
        json={
            "company_name": "Other GmbH",
            "name": "Olaf",
            "email": "olaf@other.example",
            "password": "password123",
        },
    )
    other = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = await client.get(f"/api/operations/shipments/{ref}", headers=other)
    assert r.status_code == 404
    r = await client.get(f"{doc_url}/file", headers=other)
    assert r.status_code == 404


async def test_website_lead(platform):
    client = platform
    ops = await login(client, "ops@halyard.example", "halyard-ops")
    r = await client.post(
        "/api/commercial/leads",
        json={
            "name": "Max Weber",
            "company": "Weber Möbel",
            "email": "max@weber.example",
            "teu_per_year": 60,
        },
    )
    assert r.status_code == 201
    r = await client.post(
        "/api/commercial/leads",
        json={
            "name": "Bot",
            "company": "Spam",
            "email": "bot@spam.example",
            "website": "http://spam",
        },
    )
    assert r.status_code == 201
    leads = (await client.get("/api/commercial/leads", headers=ops)).json()
    assert [lead["company"] for lead in leads] == ["Weber Möbel"]


async def test_one_swagger_ui_for_every_service(platform):
    client = platform

    docs = await client.get("/docs")
    spec = (await client.get("/openapi.json")).json()

    assert docs.status_code == 200 and "swagger" in docs.text.lower()
    assert spec["info"]["title"] == "Halyard API"
    for path in [
        "/api/accounts/auth/login",
        "/api/commercial/quotes",
        "/api/operations/shipments",
        "/api/billing/invoices",
        "/api/notifications/notifications",
    ]:
        assert path in spec["paths"], path
    assert list(spec["components"]["securitySchemes"]) == ["HTTPBearer"]
    ids = [
        op["operationId"]
        for ops in spec["paths"].values()
        for op in ops.values()
    ]
    assert len(ids) == len(set(ids))
