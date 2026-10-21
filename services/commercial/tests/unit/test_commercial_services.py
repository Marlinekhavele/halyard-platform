"""Tests for commercial.services."""

import datetime

import pytest
import sqlalchemy as sa

from commercial import models
from commercial import schemas
from commercial import services
from halyard_common import errors
from halyard_common import events
from halyard_common import testing

from .. import conftest

CUSTOMER = testing.customer_user()
OTHER_CUSTOMER = testing.customer_user(testing.OTHER_COMPANY_ID)
OPS = testing.ops_user()


def _request(**overrides) -> schemas.QuoteCreate:
    body = {
        "pol": "CNSHA",
        "pod": "DEHAM",
        "container_type": "40HC",
        "quantity": 2,
        "ready_date": conftest.TODAY,
        **overrides,
    }
    return schemas.QuoteCreate(**body)


async def _staged(session, event_type: str) -> list[dict]:
    rows = await session.scalars(
        sa.select(models.OutboxEvent).where(
            models.OutboxEvent.type == event_type
        )
    )
    return [row.payload["data"] for row in rows]


@pytest.fixture(name="quotes")
def fixture_quotes(make_service) -> services.QuoteService:
    return make_service(services.QuoteService)


@pytest.fixture(name="bookings")
def fixture_bookings(make_service) -> services.BookingService:
    return make_service(services.BookingService)


async def _book(quotes, user=CUSTOMER) -> models.Booking:
    quote = await quotes.create_quote(user, _request())
    return await quotes.book_option(
        user,
        quote.id,
        quote.options[0].id,
        schemas.AcceptOption(gross_weight_kg=18_400),
    )


# ---- Quotes ----------------------------------------------------------------


async def test_price_rejects_unknown_port(quotes):
    with pytest.raises(errors.InvalidRequestError, match="XXXXX"):
        await quotes.price(_request(pol="XXXXX"))


async def test_price_never_quotes_ready_dates_in_the_past(quotes):
    past = conftest.TODAY - datetime.timedelta(days=30)

    options = await quotes.price(_request(ready_date=past))

    assert all(o.etd >= conftest.TODAY for o in options)


async def test_create_quote_saves_three_options(quotes):
    quote = await quotes.create_quote(CUSTOMER, _request())

    assert quote.ref == "Q-26-00001"
    assert quote.company_id == CUSTOMER.company_id
    assert quote.valid_until == conftest.TODAY + datetime.timedelta(days=7)
    assert [o.label for o in quote.options] == [
        "Best value",
        "Fastest",
        "Lowest CO₂",
    ]


async def test_create_quote_without_rates_fails(quotes, session):
    await session.execute(sa.update(models.Rate).values(active=False))

    with pytest.raises(errors.InvalidRequestError, match="no rates"):
        await quotes.create_quote(CUSTOMER, _request())


async def test_quote_expires_after_validity(quotes, make_service):
    quote = await quotes.create_quote(CUSTOMER, _request())
    later = make_service(
        services.QuoteService, conftest.TODAY + datetime.timedelta(days=8)
    )

    assert quote.status_on(later.today()) == "expired"
    with pytest.raises(errors.ConflictError, match="expired"):
        await later.book_option(
            CUSTOMER,
            quote.id,
            quote.options[0].id,
            schemas.AcceptOption(gross_weight_kg=1000),
        )


async def test_quotes_are_scoped_to_company(quotes):
    await quotes.create_quote(CUSTOMER, _request())
    await quotes.create_quote(OTHER_CUSTOMER, _request())

    assert len(await quotes.list_quotes(CUSTOMER, 50)) == 1
    assert len(await quotes.list_quotes(OPS, 50)) == 2


async def test_get_quote_hides_other_companies(quotes):
    quote = await quotes.create_quote(CUSTOMER, _request())

    with pytest.raises(errors.NotFoundError):
        await quotes.get_quote(OTHER_CUSTOMER, quote.id)


# ---- Booking ---------------------------------------------------------------


async def test_book_option_creates_request_and_event(quotes, session):
    booking = await _book(quotes)

    assert booking.ref == "HLY-26-00001"
    assert booking.status == "requested"
    assert (await quotes.quotes.get(booking.quote_id)).status == "accepted"
    [event] = await _staged(session, events.EventType.BOOKING_REQUESTED)
    assert event["booking_ref"] == booking.ref


async def test_quote_can_only_be_booked_once(quotes):
    booking = await _book(quotes)

    with pytest.raises(errors.ConflictError, match="already been booked"):
        await quotes.book_option(
            CUSTOMER,
            booking.quote_id,
            booking.option_id,
            schemas.AcceptOption(gross_weight_kg=1000),
        )


async def test_other_company_cannot_book_quote(quotes):
    quote = await quotes.create_quote(CUSTOMER, _request())

    with pytest.raises(errors.NotFoundError):
        await quotes.book_option(
            OTHER_CUSTOMER,
            quote.id,
            quote.options[0].id,
            schemas.AcceptOption(gross_weight_kg=1000),
        )


async def test_unknown_option_is_not_found(quotes):
    quote = await quotes.create_quote(CUSTOMER, _request())

    with pytest.raises(errors.NotFoundError, match="Option"):
        await quotes.book_option(
            CUSTOMER,
            quote.id,
            "nope",
            schemas.AcceptOption(gross_weight_kg=1000),
        )


async def test_confirm_shifts_eta_with_new_etd(quotes, bookings, session):
    booking = await _book(quotes)
    old_etd, old_eta = booking.etd, booking.eta
    new_etd = old_etd + datetime.timedelta(days=3)

    confirmed = await bookings.confirm(
        OPS,
        booking.id,
        schemas.ConfirmBooking(vessel="Elbe", voyage="052W", etd=new_etd),
    )

    assert confirmed.status == "confirmed"
    assert confirmed.eta == old_eta + datetime.timedelta(days=3)
    assert confirmed.confirmed_by == OPS.email
    [event] = await _staged(session, events.EventType.BOOKING_CONFIRMED)
    assert event["pol_name"] == "Shanghai"
    assert event["pod_name"] == "Hamburg"
    assert event["lines"]


async def test_confirm_is_ops_only_and_once(quotes, bookings):
    booking = await _book(quotes)
    confirmation = schemas.ConfirmBooking(vessel="Elbe", voyage="052W")

    with pytest.raises(errors.PermissionDeniedError):
        await bookings.confirm(CUSTOMER, booking.id, confirmation)
    await bookings.confirm(OPS, booking.id, confirmation)
    with pytest.raises(errors.ConflictError, match="already confirmed"):
        await bookings.confirm(OPS, booking.id, confirmation)


async def test_customer_cancels_only_unconfirmed_bookings(quotes, bookings):
    booking = await _book(quotes)
    await bookings.confirm(
        OPS, booking.id, schemas.ConfirmBooking(vessel="Elbe", voyage="052W")
    )

    with pytest.raises(errors.ConflictError, match="Contact your ops"):
        await bookings.cancel(CUSTOMER, booking.id, "Changed plans")
    cancelled = await bookings.cancel(OPS, booking.id, "Carrier rolled")
    assert cancelled.status == "cancelled"
    with pytest.raises(errors.ConflictError, match="already cancelled"):
        await bookings.cancel(OPS, booking.id, "Again")


async def test_bookings_are_scoped_and_filterable(quotes, bookings):
    await _book(quotes)
    await _book(quotes, OTHER_CUSTOMER)

    assert len(await bookings.list_bookings(CUSTOMER, None)) == 1
    assert len(await bookings.list_bookings(OPS, "requested")) == 2
    assert await bookings.list_bookings(OPS, "confirmed") == []


# ---- Rates and leads -------------------------------------------------------


async def test_rate_update_refuses_selling_below_cost(make_service):
    rates = make_service(services.RateService)
    [rate, *_] = await rates.list_rates(OPS, "ASIA", "EU", "40HC")

    updated = await rates.update_rate(OPS, rate.id, {"transit_days": 30})
    assert updated.transit_days == 30
    with pytest.raises(errors.InvalidRequestError, match="below buy"):
        await rates.update_rate(OPS, rate.id, {"sell_cents": 1})


async def test_rates_are_ops_only(make_service):
    rates = make_service(services.RateService)

    with pytest.raises(errors.PermissionDeniedError):
        await rates.list_rates(CUSTOMER)
    with pytest.raises(errors.PermissionDeniedError):
        await rates.list_surcharges(CUSTOMER)


def test_vessel_suggestions():
    assert "MSC Rhea" in services.RateService.vessel_suggestions("MSC")
    assert services.RateService.vessel_suggestions("Unknown") == []


async def test_leads_honeypot_and_status(make_service):
    leads = make_service(services.LeadService)
    real = schemas.LeadCreate(
        name="Max", company="Weber", email="max@weber.example"
    )
    bot = real.model_copy(update={"website": "http://spam"})

    await leads.create_lead(real)
    await leads.create_lead(bot)

    [lead] = await leads.list_leads(OPS)
    updated = await leads.update_status(OPS, lead.id, "contacted")
    assert updated.status == "contacted"
    with pytest.raises(errors.PermissionDeniedError):
        await leads.list_leads(CUSTOMER)
    with pytest.raises(errors.NotFoundError):
        await leads.update_status(OPS, "missing", "won")
