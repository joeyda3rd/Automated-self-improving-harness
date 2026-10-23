"""Money helpers. All amounts are decimal.Decimal."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from .currency import MINOR_UNITS


class MoneyError(ValueError):
    pass


def to_decimal(value):
    """Parse a price/amount from JSON or user input into a Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MoneyError(f"not an amount: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        raise MoneyError(f"not an amount: {value!r}") from None


def quantum(currency):
    """The smallest unit of `currency` as a Decimal exponent, e.g. Decimal('0.01')."""
    try:
        places = MINOR_UNITS[currency]
    except KeyError:
        raise MoneyError(f"unknown currency {currency!r}") from None
    return Decimal(1).scaleb(-places)


def round_money(amount, currency):
    """Round an amount to the minor unit of `currency`."""
    return to_decimal(amount).quantize(quantum(currency), rounding=ROUND_HALF_UP)


def cents(amount):
    """Round to whole cents."""
    return to_decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_money(amount, currency):
    """Format for display: '1,234.50 EUR', '1,235 JPY'."""
    q = round_money(amount, currency)
    places = MINOR_UNITS[currency]
    sign = "-" if q < 0 else ""
    text = f"{abs(q):,.{places}f}"
    return f"{sign}{text} {currency}"


def sum_money(amounts, currency):
    total = Decimal(0)
    for a in amounts:
        total += to_decimal(a)
    return round_money(total, currency)
