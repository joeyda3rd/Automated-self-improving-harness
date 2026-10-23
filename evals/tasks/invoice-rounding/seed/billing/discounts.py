"""Discounts: per-line percentages and customer tier discounts."""
from decimal import Decimal

from .money import round_money, to_decimal

# Percent off for each customer tier.
TIER_DISCOUNT_PCT = {
    "standard": Decimal("0"),
    "silver": Decimal("2.5"),
    "gold": Decimal("5"),
    "platinum": Decimal("12.5"),
}


class DiscountError(ValueError):
    pass


def check_pct(pct):
    pct = to_decimal(pct)
    if pct < 0 or pct > 100:
        raise DiscountError(f"discount must be between 0 and 100, got {pct}")
    return pct


def factor(pct):
    """Multiplier for a percentage discount: 12.5 -> 0.875."""
    return (Decimal(100) - check_pct(pct)) / Decimal(100)


def tier_pct(tier):
    try:
        return TIER_DISCOUNT_PCT[tier]
    except KeyError:
        raise DiscountError(f"unknown tier {tier!r}") from None


def apply_tier_discount(amount, tier, currency):
    """Apply the customer's tier discount to an invoice amount."""
    return round_money(amount * factor(tier_pct(tier)), currency)
