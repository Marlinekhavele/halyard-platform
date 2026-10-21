"""Tests for halyard_common.money."""

from halyard_common import money


def test_cents_rounds_to_whole_cents():
    assert money.cents(12.34) == 1234
    assert money.cents(19.999) == 2000
    assert money.cents(2150) == 215_000


def test_pct_of():
    assert money.pct_of(10_000, 14) == 1400
    assert money.pct_of(333, 50) == 166
