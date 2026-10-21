"""Money helpers. Money is stored as integer cents everywhere, never floats."""


def cents(euros: float) -> int:
    """Converts a euro amount to integer cents, rounding half to even.

    Args:
        euros: Amount in euros.

    Returns:
        The amount in cents.
    """
    return int(round(euros * 100))


def pct_of(amount_cents: int, percent: float) -> int:
    """Returns a percentage of an amount, rounded to whole cents.

    Args:
        amount_cents: The base amount in cents.
        percent: The percentage, for example ``14`` for 14 %.

    Returns:
        The share in cents.
    """
    return int(round(amount_cents * percent / 100))
