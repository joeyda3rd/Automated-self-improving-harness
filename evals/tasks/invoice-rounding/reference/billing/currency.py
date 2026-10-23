"""Currencies and exchange rates.

RATES holds the bank's published cross rates: 1 unit of the first currency is worth
that many units of the second. These numbers are correct and must not be changed.
"""
from decimal import Decimal

MINOR_UNITS = {"USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}

RATES = {
    ("EUR", "USD"): Decimal("1.0832"), ("USD", "EUR"): Decimal("0.9232"),
    ("GBP", "USD"): Decimal("1.2645"), ("USD", "GBP"): Decimal("0.7908"),
    ("JPY", "USD"): Decimal("0.006712"), ("USD", "JPY"): Decimal("148.97"),
    ("EUR", "GBP"): Decimal("0.8561"), ("GBP", "EUR"): Decimal("1.1681"),
    ("EUR", "JPY"): Decimal("161.38"), ("JPY", "EUR"): Decimal("0.006197"),
    ("GBP", "JPY"): Decimal("188.42"), ("JPY", "GBP"): Decimal("0.005308"),
}


class CurrencyError(ValueError):
    pass


def check_currency(code):
    if code not in MINOR_UNITS:
        raise CurrencyError(f"unsupported currency {code!r}")
    return code


def rate(src, dst):
    """Exchange rate from `src` to `dst` as a Decimal."""
    check_currency(src)
    check_currency(dst)
    if src == dst:
        return Decimal(1)
    try:
        return RATES[(src, dst)]
    except KeyError:
        raise CurrencyError(f"no rate {src}->{dst}") from None


def convert(amount, src, dst):
    """Convert `amount` from `src` to `dst` (unrounded)."""
    return amount * rate(src, dst)
