"""Tests for commercial.repositories against seeded data."""

import datetime

from commercial import repositories
from commercial.core import seed

from .. import conftest


async def test_reference_data_is_seeded_once(session):
    assert not await seed.add_reference_data(session, conftest.TODAY)
    assert await repositories.PortRepository(session).count() > 20


async def test_find_bookable_filters_lane_type_and_validity(session):
    rates = repositories.RateRepository(session)

    found = await rates.find_bookable("ASIA", "EU", "40HC", conftest.TODAY)

    assert len(found) == 3  # One per product profile.
    assert all(r.container_type == "40HC" for r in found)
    assert all(
        (r.origin_region, r.dest_region) == ("ASIA", "EU") for r in found
    )


async def test_find_bookable_skips_inactive_and_expired(session):
    rates = repositories.RateRepository(session)
    first, second, _ = await rates.find_bookable(
        "ASIA", "EU", "40HC", conftest.TODAY
    )
    first.active = False
    second.valid_until = conftest.TODAY - datetime.timedelta(days=1)
    await session.flush()

    found = await rates.find_bookable("ASIA", "EU", "40HC", conftest.TODAY)

    assert len(found) == 1


async def test_search_filters_are_optional(session):
    rates = repositories.RateRepository(session)

    everything = await rates.search()
    reefers = await rates.search(container_type="40RF")

    assert len(reefers) * 4 == len(everything)


async def test_surcharges_in_display_order(session):
    codes = [
        s.code
        for s in await repositories.SurchargeRepository(session).list_sorted()
    ]

    assert codes[0] == "BAF"
    assert codes[-1] == "INSURANCE"


async def test_refs_count_up_per_year(session):
    quotes = repositories.QuoteRepository(session)
    bookings = repositories.BookingRepository(session)

    assert await quotes.next_ref(conftest.TODAY) == "Q-26-00001"
    assert await bookings.next_ref(conftest.TODAY) == "HLY-26-00001"
