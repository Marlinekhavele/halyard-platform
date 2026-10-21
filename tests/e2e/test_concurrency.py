"""Concurrent requests must not duplicate references or double-book.

These races only show up with a real multi-connection database, so the test
runs when ``E2E_POSTGRES`` is set (as in CI) and is skipped on SQLite.
"""

import asyncio
import collections
import datetime
import os

import pytest

from . import test_full_flow

pytestmark = pytest.mark.skipif(
    not os.environ.get("E2E_POSTGRES"), reason="needs E2E_POSTGRES"
)

platform = test_full_flow.fixture_platform

QUOTE = {
    "pol": "CNSHA",
    "pod": "DEHAM",
    "container_type": "40HC",
    "quantity": 1,
    "ready_date": str(datetime.date.today() + datetime.timedelta(days=5)),
}


async def test_simultaneous_quotes_get_unique_references(platform):
    client = platform
    customer = await test_full_flow.login(
        client, "anna@nordwerk.example", "demo1234"
    )

    results = await asyncio.gather(
        *[
            client.post("/api/commercial/quotes", json=QUOTE, headers=customer)
            for _ in range(10)
        ]
    )

    assert collections.Counter(r.status_code for r in results) == {201: 10}
    assert len({r.json()["ref"] for r in results}) == 10


async def test_simultaneous_bookings_of_one_quote(platform):
    client = platform
    customer = await test_full_flow.login(
        client, "anna@nordwerk.example", "demo1234"
    )
    quote = (
        await client.post(
            "/api/commercial/quotes", json=QUOTE, headers=customer
        )
    ).json()
    url = (
        f"/api/commercial/quotes/{quote['id']}"
        f"/options/{quote['options'][0]['id']}/book"
    )

    results = await asyncio.gather(
        *[
            client.post(url, json={"gross_weight_kg": 9000}, headers=customer)
            for _ in range(2)
        ]
    )

    assert sorted(r.status_code for r in results) == [201, 409]
