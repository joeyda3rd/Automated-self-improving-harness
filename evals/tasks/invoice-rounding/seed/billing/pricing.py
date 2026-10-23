"""Pricing of individual order lines."""
from .discounts import factor
from .money import round_money


class PricingError(ValueError):
    pass


def check_qty(qty):
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        raise PricingError(f"quantity must be a positive integer, got {qty!r}")
    return qty


def gross(product, line):
    """Undiscounted price of a line, in the product's currency."""
    return round_money(product.unit_price * check_qty(line.qty), product.currency)


def line_net(product, line):
    """Line price after the line's own discount, in the product's currency."""
    return round_money(gross(product, line) * factor(line.discount_pct), product.currency)
