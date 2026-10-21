"""Sales tax / VAT by customer region and product tax class."""
from decimal import Decimal

from .money import round_money

TAX_RATES = {
    "US-CA": {"standard": Decimal("0.0725"), "food": Decimal("0"), "digital": Decimal("0.0725")},
    "US-OR": {"standard": Decimal("0"), "food": Decimal("0"), "digital": Decimal("0")},
    "DE": {"standard": Decimal("0.19"), "food": Decimal("0.07"), "digital": Decimal("0.19")},
    "UK": {"standard": Decimal("0.20"), "food": Decimal("0"), "digital": Decimal("0.20")},
    "JP": {"standard": Decimal("0.10"), "food": Decimal("0.08"), "digital": Decimal("0.10")},
}


class TaxError(KeyError):
    pass


def tax_rate(region, tax_class):
    try:
        return TAX_RATES[region][tax_class]
    except KeyError:
        raise TaxError(f"no tax rate for {region}/{tax_class}") from None


def line_tax(amount, region, tax_class, currency):
    """Tax on one invoice line, rounded to the minor unit of `currency`."""
    return round_money(amount * tax_rate(region, tax_class), currency)
