"""Pricing of individual order lines. Results are exact (unrounded)."""
from .discounts import factor


class PricingError(ValueError):
    pass


def check_qty(qty):
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        raise PricingError(f"quantity must be a positive integer, got {qty!r}")
    return qty


def gross(product, line):
    """Undiscounted price of a line, in the product's currency (exact)."""
    return product.unit_price * check_qty(line.qty)


def line_net(product, line, tier_pct=0):
    """Line price after the line's discount and the tier discount, in the product's currency (exact)."""
    return gross(product, line) * factor(line.discount_pct) * factor(tier_pct)
