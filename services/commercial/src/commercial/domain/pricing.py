"""Quote engine: turns rates and surcharges into priced shipping options.

Pure functions with no database access, so they are easy to test and reason
about. All amounts are integer cents.
"""

import dataclasses
import datetime

from commercial.domain import reference

# Rough well-to-wake estimate per TEU per sea day. Replace with carrier or GLEC
# figures.
CO2_KG_PER_TEU_DAY = 72


@dataclasses.dataclass(frozen=True)
class RateInput:
    """The parts of a stored rate the engine needs."""

    id: str
    carrier: str
    service: str
    via_port: str | None
    container_type: str
    buy_cents: int
    sell_cents: int
    transit_days: int
    sailing_weekday: int
    co2_factor: float


@dataclasses.dataclass(frozen=True)
class SurchargeInput:
    """The parts of a stored surcharge the engine needs."""

    code: str
    label: str
    basis: str
    sell_value: int
    cost_value: int
    min_sell_cents: int = 0
    min_cost_cents: int = 0
    container_type: str | None = None
    option: str | None = None
    sort: int = 100


@dataclasses.dataclass(frozen=True)
class QuoteRequest:
    """What the customer wants to ship."""

    container_type: str
    quantity: int
    ready_date: datetime.date
    cargo_value_cents: int = 0
    customs: bool = False
    trucking: bool = False
    insurance: bool = False


@dataclasses.dataclass
class Line:
    """One charge of a priced option."""

    code: str
    label: str
    quantity: int
    sell_cents: int
    cost_cents: int

    def as_dict(self) -> dict:
        """Returns the line as a JSON-serialisable dict."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PricedOption:
    """A rate priced for one request, with schedule and CO2 estimate."""

    label: str
    rate: RateInput
    etd: datetime.date
    eta: datetime.date
    transit_days: int
    co2_kg: int
    lines: list[Line] = dataclasses.field(default_factory=list)

    @property
    def total_sell_cents(self) -> int:
        """What the customer pays."""
        return sum(line.sell_cents for line in self.lines)

    @property
    def total_cost_cents(self) -> int:
        """What we pay our partners."""
        return sum(line.cost_cents for line in self.lines)

    @property
    def margin_cents(self) -> int:
        """Gross profit on this option."""
        return self.total_sell_cents - self.total_cost_cents


def next_sailing(
    ready: datetime.date, weekday: int, handling_days: int = 2
) -> datetime.date:
    """Returns the first sailing after the cargo can reach the port.

    Args:
        ready: When the cargo is ready at the supplier.
        weekday: The carrier's sailing weekday, 0 = Monday.
        handling_days: Days needed to get the cargo to the port.

    Returns:
        The departure date.
    """
    earliest = ready + datetime.timedelta(days=handling_days)
    return earliest + datetime.timedelta(
        days=(weekday - earliest.weekday()) % 7
    )


def _surcharge_amounts(
    surcharge: SurchargeInput,
    req: QuoteRequest,
    ocean_sell: int,
    ocean_cost: int,
) -> tuple[int, int, int]:
    """Returns ``(sell, cost, quantity)`` of one surcharge for a request.

    Raises:
        ValueError: The surcharge basis is unknown.
    """
    qty = req.quantity
    if surcharge.basis == "per_container":
        return surcharge.sell_value * qty, surcharge.cost_value * qty, qty
    if surcharge.basis == "per_shipment":
        return surcharge.sell_value, surcharge.cost_value, 1
    if surcharge.basis == "percent_ocean":
        sell = round(ocean_sell * surcharge.sell_value / 10_000)
        cost = round(ocean_cost * surcharge.cost_value / 10_000)
        return sell, cost, 1
    if surcharge.basis == "percent_value":
        value = req.cargo_value_cents
        sell = max(
            surcharge.min_sell_cents,
            round(value * surcharge.sell_value / 10_000),
        )
        cost = max(
            surcharge.min_cost_cents,
            round(value * surcharge.cost_value / 10_000),
        )
        return sell, cost, 1
    raise ValueError(f"Unknown surcharge basis {surcharge.basis}")


def price_rate(
    rate: RateInput,
    surcharges: list[SurchargeInput],
    req: QuoteRequest,
    label: str,
) -> PricedOption:
    """Prices one rate for a request.

    Args:
        rate: The ocean rate.
        surcharges: Every surcharge; those not applicable are skipped.
        req: The customer's request.
        label: Label of the resulting option.

    Returns:
        The priced option.

    Raises:
        ValueError: A surcharge has an unknown basis.
    """
    qty = req.quantity
    ocean_sell = rate.sell_cents * qty
    ocean_cost = rate.buy_cents * qty
    lines = [
        Line(
            "OCEAN",
            f"Ocean freight ({qty}× {req.container_type})",
            qty,
            ocean_sell,
            ocean_cost,
        )
    ]

    chosen = {
        "customs": req.customs,
        "trucking": req.trucking,
        "insurance": req.insurance,
    }
    for surcharge in sorted(surcharges, key=lambda s: s.sort):
        if (
            surcharge.container_type
            and surcharge.container_type != req.container_type
        ):
            continue
        if surcharge.option and not chosen.get(surcharge.option):
            continue
        sell, cost, quantity = _surcharge_amounts(
            surcharge, req, ocean_sell, ocean_cost
        )
        lines.append(
            Line(surcharge.code, surcharge.label, quantity, sell, cost)
        )

    etd = next_sailing(req.ready_date, rate.sailing_weekday)
    eta = etd + datetime.timedelta(days=rate.transit_days)
    teu = reference.CONTAINER_TEU[req.container_type] * qty
    co2_kg = round(
        teu * rate.transit_days * CO2_KG_PER_TEU_DAY * rate.co2_factor
    )
    return PricedOption(label, rate, etd, eta, rate.transit_days, co2_kg, lines)


def build_options(
    rates: list[RateInput],
    surcharges: list[SurchargeInput],
    req: QuoteRequest,
) -> list[PricedOption]:
    """Offers up to three options: best value, fastest and lowest CO2.

    The same rate is never offered twice.

    Args:
        rates: Candidate rates on the lane.
        surcharges: Every surcharge.
        req: The customer's request.

    Returns:
        The options, possibly empty.
    """
    candidates = [r for r in rates if r.container_type == req.container_type]
    if not candidates:
        return []
    priced = [price_rate(r, surcharges, req, "") for r in candidates]

    picks: list[tuple[str, PricedOption]] = [
        ("Best value", min(priced, key=lambda o: (o.total_sell_cents, o.eta))),
        ("Fastest", min(priced, key=lambda o: (o.eta, o.total_sell_cents))),
        (
            "Lowest CO₂",
            min(priced, key=lambda o: (o.co2_kg, o.total_sell_cents)),
        ),
    ]
    seen: set[str] = set()
    options: list[PricedOption] = []
    for label, option in picks:
        if option.rate.id in seen:
            continue
        seen.add(option.rate.id)
        option.label = label
        options.append(option)
    return options
