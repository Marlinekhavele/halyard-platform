"""Fills a running Halyard with realistic demo shipments via the real APIs.

Everything goes through the gateway exactly as a client would: quotes,
bookings, ops confirmation, tracking events, document uploads and invoices.
Safe to run twice (skips if data exists).

    python scripts/seed_demo.py                     # http://localhost:8080
    python scripts/seed_demo.py --base http://host  # another environment
"""

import argparse
from collections.abc import Callable, Iterable
import datetime
import sys
import time
from typing import Any

import httpx

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
CUSTOMER_LOGIN = ("anna@nordwerk.example", "demo1234")
OPS_LOGIN = ("ops@halyard.example", "halyard-ops")
PRE_DEPARTURE_DOCS = (
    "COMMERCIAL_INVOICE",
    "PACKING_LIST",
    "SHIPPING_INSTRUCTIONS",
    "VGM",
)
LEADS = [
    {
        "name": "Jonas Richter",
        "company": "Richter Sport GmbH",
        "email": "jonas@richter-sport.example",
        "origin": "Shanghai",
        "destination": "Hamburg",
        "teu_per_year": 80,
        "message": (
            "We import bikes and accessories, about 40 containers a year."
            " Current forwarder is slow to quote."
        ),
    },
    {
        "name": "Mira Schulz",
        "company": "Casa Mira Home",
        "email": "mira@casamira.example",
        "origin": "Ho Chi Minh City",
        "destination": "Hamburg",
        "teu_per_year": 24,
        "message": (
            "Furniture, FOB. Looking for someone who handles customs and"
            " delivery to Berlin."
        ),
    },
]

Headers = dict[str, str]


def days(n: int) -> datetime.timedelta:
    """Returns a timedelta of ``n`` days."""
    return datetime.timedelta(days=n)


def at(day: datetime.date, hour: int = 10) -> str:
    """Returns an ISO timestamp at a whole hour UTC on a day."""
    return datetime.datetime.combine(
        day, datetime.time(hour), tzinfo=datetime.UTC
    ).isoformat()


class Api:
    """Thin client for the gateway's ``/api`` routes."""

    def __init__(self, base: str) -> None:
        """Initialises the client.

        Args:
            base: Gateway URL, for example ``http://localhost:8080``.
        """
        self.http = httpx.Client(base_url=base.rstrip("/") + "/api", timeout=30)

    def wait_until_healthy(self, attempts: int = 60) -> None:
        """Waits for the gateway and the services to answer."""
        for _ in range(attempts):
            try:
                if all(
                    self.http.get(f"/{s}/health").status_code == 200
                    for s in ("accounts", "operations")
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2)

    def login(self, email: str, password: str) -> Headers:
        """Signs in and returns the ``Authorization`` header."""
        r = self.http.post(
            "/accounts/auth/login", json={"email": email, "password": password}
        )
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def call(self, method: str, path: str, headers: Headers, **kw: Any) -> Any:
        """Sends a request and returns the JSON body.

        Raises:
            RuntimeError: The API answered with an error status.
        """
        r = self.http.request(method, path, headers=headers, **kw)
        if r.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} -> {r.status_code}: {r.text[:300]}"
            )
        return r.json()

    def wait_for(
        self, fn: Callable[[], Any], what: str, timeout: float = 20
    ) -> Any:
        """Polls until ``fn`` returns something truthy.

        Raises:
            RuntimeError: ``fn`` did not succeed in time.
        """
        end = time.time() + timeout
        while time.time() < end:
            try:
                value = fn()
                if value:
                    return value
            except RuntimeError:
                pass
            time.sleep(0.3)
        raise RuntimeError(f"timed out waiting for {what}")


class Seeder:
    """Builds the demo scenarios as the customer and the ops team."""

    def __init__(self, api: Api) -> None:
        """Signs in both demo users.

        Args:
            api: The API client.
        """
        self.api = api
        self.customer = api.login(*CUSTOMER_LOGIN)
        self.ops = api.login(*OPS_LOGIN)
        self.today = datetime.date.today()

    def already_seeded(self) -> bool:
        """Whether the demo customer already has shipments."""
        return bool(
            self.api.call("GET", "/operations/shipments", self.customer)
        )

    def book(
        self,
        route: tuple[str, str, str, int],
        commodity: str,
        value_eur: int,
        weight_kg: int,
        supplier: str,
        option: int = 0,
        incoterm: str = "FOB",
        extras: bool = True,
    ) -> dict:
        """Requests a quote and books one of its options as the customer.

        Args:
            route: ``(pol, pod, container_type, quantity)``.
            commodity: What is shipped.
            value_eur: Cargo value.
            weight_kg: Gross weight.
            supplier: The shipper.
            option: Index of the option to book.
            incoterm: The incoterm.
            extras: Add customs clearance and trucking.

        Returns:
            The booking.
        """
        pol, pod, ctype, quantity = route
        quote = self.api.call(
            "POST",
            "/commercial/quotes",
            self.customer,
            json={
                "pol": pol,
                "pod": pod,
                "container_type": ctype,
                "quantity": quantity,
                "ready_date": str(self.today),
                "incoterm": incoterm,
                "commodity": commodity,
                "cargo_value_cents": value_eur * 100,
                "customs": extras,
                "trucking": extras,
                "insurance": True,
            },
        )
        chosen = quote["options"][min(option, len(quote["options"]) - 1)]
        return self.api.call(
            "POST",
            f"/commercial/quotes/{quote['id']}/options/{chosen['id']}/book",
            self.customer,
            json={"gross_weight_kg": weight_kg, "supplier_name": supplier},
        )

    def confirm(
        self,
        booking: dict,
        vessel: str,
        voyage: str,
        etd: datetime.date,
        transit_days: int,
    ) -> dict:
        """Confirms a booking as ops and waits for its shipment."""
        self.api.call(
            "POST",
            f"/commercial/bookings/{booking['id']}/confirm",
            self.ops,
            json={
                "vessel": vessel,
                "voyage": voyage,
                "etd": str(etd),
                "eta": str(etd + days(transit_days)),
            },
        )
        return self.api.wait_for(
            lambda: self.shipment(booking["ref"]), f"shipment {booking['ref']}"
        )

    def shipment(self, ref: str) -> dict:
        """Returns a shipment as ops sees it."""
        return self.api.call("GET", f"/operations/shipments/{ref}", self.ops)

    def step(self, ref: str, event: str, when: datetime.date, **extra) -> dict:
        """Simulates a tracking event for every container of a shipment."""
        return self.api.call(
            "POST",
            f"/operations/shipments/{ref}/simulate",
            self.ops,
            json={"event": event, "occurred_at": at(when), **extra},
        )

    def upload(
        self, shipment: dict, doc_type: str, by_ops: bool = False
    ) -> dict:
        """Uploads a PDF for a document; returns the document."""
        doc = next(
            d for d in shipment["documents"] if d["doc_type"] == doc_type
        )
        self.api.call(
            "POST",
            f"/operations/documents/{doc['id']}/upload",
            self.ops if by_ops else self.customer,
            files={"file": (f"{doc_type.lower()}.pdf", PDF, "application/pdf")},
        )
        return doc

    def review(self, doc: dict, approve: bool, note: str | None = None) -> None:
        """Reviews a customer upload as ops."""
        self.api.call(
            "POST",
            f"/operations/documents/{doc['id']}/review",
            self.ops,
            json={"approve": approve, "note": note},
        )

    def paperwork(
        self, shipment: dict, doc_types: Iterable[str] = PRE_DEPARTURE_DOCS
    ) -> None:
        """Uploads documents as the customer and approves them as ops."""
        for doc_type in doc_types:
            self.review(self.upload(shipment, doc_type), approve=True)

    # ---- Scenarios ---------------------------------------------------------

    def at_sea(self) -> None:
        """Shanghai to Hamburg, past transshipment."""
        b = self.book(
            ("CNSHA", "DEHAM", "40HC", 2),
            "Bicycle components",
            86_000,
            18_400,
            "Shanghai Velo Parts Co.",
        )
        etd = self.today - days(23)
        self.paperwork(self.confirm(b, "Elbe Meridian", "052W", etd, 34))
        for event, when in [
            ("GATE_IN", etd - days(3)),
            ("LOADED", etd - days(1)),
            ("DEPARTED", etd),
            ("TRANSSHIPMENT", etd + days(15)),
        ]:
            self.step(b["ref"], event, when)
        print("in transit:", b["ref"])

    def customs_hold(self) -> None:
        """Ningbo to Rotterdam, arrived and held; invoice sent back."""
        b = self.book(
            ("CNNGB", "NLRTM", "40HC", 1),
            "LED panels",
            41_000,
            9_800,
            "Ningbo Bright Lighting Ltd.",
            incoterm="CIF",
        )
        etd = self.today - days(36)
        s = self.confirm(b, "CMA CGM Lys Horizon", "0FL4MW", etd, 35)
        self.paperwork(s, PRE_DEPARTURE_DOCS[1:])
        self.review(
            self.upload(s, "COMMERCIAL_INVOICE"),
            approve=False,
            note=(
                "Customs needs the invoice with your EORI DE4127738100 as"
                " importer of record."
            ),
        )
        for event, when in [
            ("DEPARTED", etd),
            ("ARRIVED", etd + days(35)),
            ("DISCHARGED", etd + days(36)),
        ]:
            self.step(b["ref"], event, when)
        self.step(
            b["ref"],
            "CUSTOMS_HOLD",
            self.today - days(1),
            reason=(
                "Dutch customs found a mismatch between the EORI on the"
                " invoice and the importer of record."
            ),
        )
        print("customs hold:", b["ref"])

    def booked(self) -> None:
        """Hamburg to New York; instructions and VGM due soon."""
        b = self.book(
            ("DEHAM", "USNYC", "20DV", 3),
            "Industrial valves",
            120_000,
            41_200,
            "Nordwerk Trading GmbH",
            incoterm="FCA",
            extras=False,
        )
        etd = self.today + days(4)
        s = self.confirm(b, "MSC Aldea Norte", "FA640W", etd, 11)
        self.paperwork(s, PRE_DEPARTURE_DOCS[:2])
        self.step(b["ref"], "EMPTY_PICKUP", self.today - days(1))
        print("booked:", b["ref"])

    def delayed_reefer(self) -> None:
        """Nhava Sheva to Antwerp reefer, late; B/L waits for approval."""
        b = self.book(
            ("INNSA", "BEANR", "40RF", 1),
            "Frozen shrimp, set to −18 °C",
            64_000,
            24_000,
            "Konkan Seafoods Pvt. Ltd.",
            incoterm="CFR",
        )
        etd = self.today - days(20)
        s = self.confirm(b, "Maersk Tangier", "238W", etd, 24)
        self.paperwork(s, [*PRE_DEPARTURE_DOCS, "TEMPERATURE_INSTRUCTIONS"])
        self.step(b["ref"], "DEPARTED", etd)
        self.step(b["ref"], "TRANSSHIPMENT", etd + days(12))
        self.step(
            b["ref"],
            "ETA_CHANGED",
            self.today - days(2),
            new_eta=str(etd + days(26)),
            reason=(
                "Berth congestion at Salalah. The reefer has held −18.2 °C"
                " throughout."
            ),
        )
        self.upload(self.shipment(b["ref"]), "BILL_OF_LADING", by_ops=True)
        print("delayed:", b["ref"])

    def delivered_and_paid(self) -> None:
        """Ho Chi Minh City to Hamburg, delivered; invoice paid."""
        b = self.book(
            ("VNSGN", "DEHAM", "40HC", 2),
            "Oak furniture",
            58_000,
            15_600,
            "Saigon Timberworks JSC",
        )
        etd = self.today - days(62)
        self.paperwork(self.confirm(b, "ONE Bright Kestrel", "071W", etd, 34))
        self.step(b["ref"], "DEPARTED", etd)
        for event, offset in [
            ("TRANSSHIPMENT", 10),
            ("ARRIVED", 34),
            ("DISCHARGED", 35),
            ("CUSTOMS_RELEASED", 36),
            ("DELIVERED", 38),
        ]:
            self.step(b["ref"], event, etd + days(offset))
        print("delivered:", b["ref"])

        def issued_invoice() -> dict | None:
            invoices = self.api.call("GET", "/billing/invoices", self.ops)
            return next(
                (
                    i
                    for i in invoices
                    if i["shipment_ref"] == b["ref"] and i["status"] == "issued"
                ),
                None,
            )

        invoice = self.api.wait_for(issued_invoice, "invoice to be issued")
        self.api.call(
            "POST", f"/billing/invoices/{invoice['id']}/mark-paid", self.ops
        )

    def awaiting_confirmation(self) -> None:
        """A fresh request for the ops team to confirm."""
        b = self.book(
            ("CNSZX", "DEHAM", "40HC", 1),
            "Kitchen appliances",
            33_000,
            11_200,
            "Shenzhen HomeTech Co.",
            option=1,
        )
        print("awaiting confirmation:", b["ref"])

    def leads(self) -> None:
        """Website contact form submissions."""
        for lead in LEADS:
            self.api.call("POST", "/commercial/leads", {}, json=lead)


def main() -> None:
    """Seeds every demo scenario unless shipments already exist."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    args = parser.parse_args()
    api = Api(args.base)
    api.wait_until_healthy()

    seeder = Seeder(api)
    if seeder.already_seeded():
        print("demo shipments already exist; nothing to do")
        return
    seeder.at_sea()
    seeder.customs_hold()
    seeder.booked()
    seeder.delayed_reefer()
    seeder.delivered_and_paid()
    seeder.awaiting_confirmation()
    seeder.leads()
    print(
        "demo data ready: sign in as {} / {} or {} / {}".format(
            *CUSTOMER_LOGIN, *OPS_LOGIN
        )
    )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
