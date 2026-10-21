"""Tests for the pure quote engine in commercial.pricing."""

import datetime

import pytest

from commercial.domain import pricing

READY = datetime.date(2026, 10, 5)

RATES = [
    pricing.RateInput(
        "fast", "Maersk", "direct", None, "40HC", 230_000, 240_000, 29, 0, 1.08
    ),
    pricing.RateInput(
        "value", "MSC", "transshipment", "SGSIN", "40HC",
        193_000, 202_000, 34, 3, 1.0,
    ),
    pricing.RateInput(
        "eco", "CMA CGM", "direct", None, "40HC", 205_000, 215_000, 37, 5, 0.78
    ),
]  # fmt: skip
SURCHARGES = [
    pricing.SurchargeInput(
        "BAF", "Bunker", "percent_ocean", 1400, 1400, sort=20
    ),
    pricing.SurchargeInput(
        "THC_O", "Origin THC", "per_container", 18_500, 17_000, sort=30
    ),
    pricing.SurchargeInput("DOC", "Docs", "per_shipment", 4_500, 0, sort=70),
    pricing.SurchargeInput(
        "REEFER", "Reefer", "per_container", 14_000, 11_000,
        container_type="40RF", sort=60,
    ),
    pricing.SurchargeInput(
        "INSURANCE", "Insurance", "percent_value", 25, 16, 3_500, 2_000,
        option="insurance", sort=100,
    ),
]  # fmt: skip


def _line(option: pricing.PricedOption, code: str) -> pricing.Line:
    return next(line for line in option.lines if line.code == code)


def test_next_sailing_waits_for_carrier_weekday():
    # Ready Friday 2 Oct 2026 + 2 handling days = Sunday; Monday is 5 Oct.
    assert pricing.next_sailing(datetime.date(2026, 10, 2), 0) == (
        datetime.date(2026, 10, 5)
    )
    # The earliest day already is the sailing day.
    assert pricing.next_sailing(datetime.date(2026, 10, 3), 0) == (
        datetime.date(2026, 10, 5)
    )


def test_price_lines_and_totals():
    req = pricing.QuoteRequest(
        "40HC", 2, READY, cargo_value_cents=8_600_000, insurance=True
    )

    option = pricing.price_rate(RATES[1], SURCHARGES, req, "Best value")

    # No reefer line on a dry box.
    assert [ln.code for ln in option.lines] == [
        "OCEAN", "BAF", "THC_O", "DOC", "INSURANCE",
    ]  # fmt: skip
    assert _line(option, "OCEAN").sell_cents == 404_000
    assert _line(option, "BAF").sell_cents == 56_560
    # 0.25 % of €86,000.
    assert _line(option, "INSURANCE").sell_cents == 21_500
    assert option.total_sell_cents == sum(ln.sell_cents for ln in option.lines)
    assert option.margin_cents > 0


def test_reefer_surcharge_only_on_reefers():
    req = pricing.QuoteRequest("40RF", 1, READY)
    reefer_rate = pricing.RateInput(
        "r", "MSC", "direct", None, "40RF", 1, 2, 30, 0, 1.0
    )

    option = pricing.price_rate(reefer_rate, SURCHARGES, req, "")

    assert _line(option, "REEFER").sell_cents == 14_000


def test_insurance_minimum_and_optional_services():
    req = pricing.QuoteRequest(
        "40HC", 1, READY, cargo_value_cents=100_000, insurance=True
    )
    option = pricing.price_rate(RATES[0], SURCHARGES, req, "")
    assert _line(option, "INSURANCE").sell_cents == 3_500

    no_insurance = pricing.price_rate(
        RATES[0], SURCHARGES, pricing.QuoteRequest("40HC", 1, READY), ""
    )
    assert "INSURANCE" not in [ln.code for ln in no_insurance.lines]


def test_schedule_and_co2():
    req = pricing.QuoteRequest("40HC", 1, READY)

    option = pricing.price_rate(RATES[0], [], req, "")

    assert option.etd == datetime.date(2026, 10, 12)  # Next Monday sailing.
    assert option.eta == option.etd + datetime.timedelta(days=29)
    assert option.co2_kg == round(2 * 29 * pricing.CO2_KG_PER_TEU_DAY * 1.08)


def test_unknown_surcharge_basis_raises():
    bad = pricing.SurchargeInput("X", "X", "per_banana", 1, 1)

    with pytest.raises(ValueError, match="per_banana"):
        pricing.price_rate(
            RATES[0], [bad], pricing.QuoteRequest("40HC", 1, READY), ""
        )


def test_three_distinct_options():
    options = pricing.build_options(
        RATES, SURCHARGES, pricing.QuoteRequest("40HC", 1, READY)
    )

    assert [(o.label, o.rate.id) for o in options] == [
        ("Best value", "value"),
        ("Fastest", "fast"),
        ("Lowest CO₂", "eco"),
    ]


def test_same_rate_is_offered_once():
    options = pricing.build_options(
        RATES[:1], SURCHARGES, pricing.QuoteRequest("40HC", 1, READY)
    )

    assert [o.label for o in options] == ["Best value"]


def test_no_rates_for_container_type():
    req = pricing.QuoteRequest("20DV", 1, READY)

    assert pricing.build_options(RATES, SURCHARGES, req) == []
