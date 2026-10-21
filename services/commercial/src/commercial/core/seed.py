"""Reference data (ports, rates, surcharges) created on first start."""

import datetime

from sqlalchemy.ext import asyncio as sa_asyncio

from commercial import models
from commercial import repositories
from commercial.domain import reference
from halyard_common import service as service_lib

RATE_VALIDITY_DAYS = 365


def build_rates(valid_until: datetime.date) -> list[models.Rate]:
    """Builds the planning rates: every lane, profile and container type.

    Carriers are spread across lanes deterministically so the same database
    is produced on every run.

    Args:
        valid_until: Validity of every rate.

    Returns:
        The rates, not yet persisted.
    """
    rates = []
    for (origin, dest), (base_eur, days) in reference.LANES.items():
        seed_index = sum(map(ord, origin + dest))
        for index, profile in enumerate(reference.PROFILES):
            _, multiplier, delta, direct, co2, weekday = profile
            carriers = reference.CARRIERS
            carrier = carriers[(seed_index + index * 3) % len(carriers)]
            via = None if direct else reference.HUB_FOR_LANE.get((origin, dest))
            for ctype, factor in reference.CONTAINER_FACTORS.items():
                sell = round(base_eur * factor * multiplier * 100)
                rates.append(
                    models.Rate(
                        origin_region=origin,
                        dest_region=dest,
                        carrier=carrier,
                        service="direct" if via is None else "transshipment",
                        via_port=via,
                        container_type=ctype,
                        sell_cents=sell,
                        buy_cents=round(sell * reference.OCEAN_BUY_RATIO),
                        transit_days=max(2, days + delta),
                        sailing_weekday=weekday,
                        co2_factor=co2,
                        valid_until=valid_until,
                    )
                )
    return rates


async def add_reference_data(
    session: sa_asyncio.AsyncSession, today: datetime.date
) -> bool:
    """Adds ports, rates and surcharges if there are no ports yet.

    Does not commit.

    Args:
        session: The transaction to add to.
        today: Rates are valid for a year from this date.

    Returns:
        True if data was added; False if it already existed.
    """
    ports = repositories.PortRepository(session)
    if await ports.count():
        return False
    await ports.add_all(
        models.Port(code=c, name=n, country=cc, region=r, is_hub=h)
        for c, n, cc, r, h in reference.PORTS
    )
    valid_until = today + datetime.timedelta(days=RATE_VALIDITY_DAYS)
    await repositories.RateRepository(session).add_all(build_rates(valid_until))
    await repositories.SurchargeRepository(session).add_all(
        models.Surcharge(
            code=code,
            label=label,
            basis=basis,
            sell_value=sell,
            cost_value=cost,
            min_sell_cents=min_sell,
            min_cost_cents=min_cost,
            container_type=ctype,
            option=option,
            sort=sort,
        )
        for (
            code,
            label,
            basis,
            sell,
            cost,
            min_sell,
            min_cost,
            ctype,
            option,
            sort,
        ) in reference.SURCHARGES
    )
    return True


async def seed_reference_data(runtime: service_lib.ServiceRuntime) -> None:
    """Seeds reference data on startup.

    Reference data is always seeded (regardless of ``seed_demo_data``)
    because the quote engine cannot work without it.

    Args:
        runtime: The started Commercial runtime.
    """
    async with runtime.db.sessionmaker() as session:
        if await add_reference_data(session, datetime.date.today()):
            await session.commit()
            runtime.log.info("seeded ports, rates and surcharges")
