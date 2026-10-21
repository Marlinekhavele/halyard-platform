"""Two simultaneous bookings of one quote: exactly one may succeed."""

import pytest
import sqlalchemy as sa

from commercial import models
from commercial import repositories
from commercial import schemas
from commercial import services
from halyard_common import db
from halyard_common import errors
from halyard_common import testing

from .. import conftest

CUSTOMER = testing.customer_user()


def _request() -> schemas.QuoteCreate:
    return schemas.QuoteCreate(
        pol="CNSHA",
        pod="DEHAM",
        container_type="40HC",
        quantity=1,
        ready_date=conftest.TODAY,
    )


async def test_claim_succeeds_only_once(session, make_service):
    quote = await make_service(services.QuoteService).create_quote(
        CUSTOMER, _request()
    )
    quotes = repositories.QuoteRepository(session)

    assert await quotes.claim_for_booking(quote.id) is True
    assert await quotes.claim_for_booking(quote.id) is False


async def test_booking_loses_the_race_cleanly(session, settings, make_service):
    quote_service = make_service(services.QuoteService)
    quote = await quote_service.create_quote(CUSTOMER, _request())
    option_id = quote.options[0].id
    assert quote.status == "open"  # This session still believes it is open.

    # Another request books the quote first, in its own transaction.
    other = db.Database(settings.database_url)
    async with other.sessionmaker() as other_session:
        await other_session.execute(
            sa.update(models.Quote)
            .where(models.Quote.id == quote.id)
            .values(status="accepted")
        )
        await other_session.commit()
    await other.dispose()

    with pytest.raises(errors.ConflictError, match="already been booked"):
        await quote_service.book_option(
            CUSTOMER,
            quote.id,
            option_id,
            schemas.AcceptOption(gross_weight_kg=1000),
        )
    bookings = await repositories.BookingRepository(session).count()
    assert bookings == 0
