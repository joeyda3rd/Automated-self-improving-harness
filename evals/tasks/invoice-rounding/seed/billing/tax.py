"""Sales tax / VAT by customer region and product tax class."""
from collections import defaultdict
from decimal import Decimal

from .money import cents

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


def line_tax(amount, region, tax_class):
    """Tax on one invoice line."""
    return cents(amount * tax_rate(region, tax_class))


class TaxAccumulator:
    """Collects taxable amounts per tax class and computes the invoice's tax."""

    def __init__(self, region):
        self.region = region
        self._by_class = defaultdict(Decimal)

    def add(self, amount, tax_class):
        tax_rate(self.region, tax_class)  # validate early
        self._by_class[tax_class] += amount

    def taxable(self, tax_class):
        return self._by_class.get(tax_class, Decimal(0))

    def total(self):
        total = Decimal(0)
        for tax_class, amount in sorted(self._by_class.items()):
            total += cents(amount * tax_rate(self.region, tax_class))
        return total
