"""Fixtures for the Billing tests."""

import datetime

import pytest

from billing import main
from billing import models
from billing import services
from billing.core import config
from halyard_common import events
from halyard_common import testing

TODAY = datetime.date(2026, 10, 20)
DEPARTED = datetime.datetime(2026, 10, 10, 18, tzinfo=datetime.UTC)


def booking_confirmed(
    booking_id: str = "booking-1",
    company_id: str = testing.CUSTOMER_COMPANY_ID,
    quantity: int = 2,
) -> events.BookingConfirmed:
    """Builds a confirmed booking worth €1,000 that costs us €800."""
    return events.BookingConfirmed(
        booking_id=booking_id,
        booking_ref=f"HLY-{booking_id}",
        company_id=company_id,
        contact_email="anna@customer.example",
        pol="CNSHA",
        pod="DEHAM",
        carrier="MSC",
        vessel="MSC Rhea",
        voyage="1W",
        etd=DEPARTED.date(),
        eta=DEPARTED.date() + datetime.timedelta(days=33),
        container_type="40HC",
        quantity=quantity,
        commodity="Bikes",
        incoterm="FOB",
        gross_weight_kg=10_000,
        cargo_value_cents=0,
        lines=[
            events.PriceLine(
                code="OCEAN",
                label="Ocean freight (2× 40HC)",
                quantity=quantity,
                sell_cents=90_000,
                cost_cents=80_000,
            ),
            events.PriceLine(
                code="DOC",
                label="Documentation fee",
                sell_cents=10_000,
                cost_cents=0,
            ),
        ],
    )


def departed(booking_id: str = "booking-1") -> events.MilestoneReached:
    """Builds the DEPARTED milestone of a booking."""
    return events.MilestoneReached(
        shipment_id="s1",
        shipment_ref=f"HLY-{booking_id}",
        booking_id=booking_id,
        company_id=testing.CUSTOMER_COMPANY_ID,
        code="DEPARTED",
        label="Departed Shanghai",
        at=DEPARTED,
    )


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.Settings:
    return config.Settings(
        database_url=testing.sqlite_url(tmp_path, "billing"),
        broker_url="memory://",
    )


@pytest.fixture(name="session")
async def fixture_session(settings):
    async with testing.database_session(
        settings.database_url, models.Base.metadata
    ) as session:
        yield session


@pytest.fixture(name="make_service")
def fixture_make_service(session, settings):
    """Returns a factory building the invoice service on a fixed date."""

    def make(today: datetime.date = TODAY, **overrides):
        return services.InvoiceService(
            session,
            settings.model_copy(update=overrides),
            today=lambda: today,
        )

    return make


@pytest.fixture(name="service")
def fixture_service(make_service) -> services.InvoiceService:
    return make_service()


@pytest.fixture(name="client")
async def fixture_client(settings):
    async with testing.running_client(main.create_app(settings)) as client:
        yield client
