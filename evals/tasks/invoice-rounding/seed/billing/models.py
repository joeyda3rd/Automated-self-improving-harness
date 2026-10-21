"""Plain data types shared across the billing package."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit_price: Decimal          # in `currency`; metered products may have sub-cent prices
    currency: str
    tax_class: str = "standard"  # standard | food | digital


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str
    currency: str                # default invoice currency
    region: str                  # tax region, see billing.tax.TAX_RATES
    tier: str = "standard"       # see billing.discounts.TIER_DISCOUNT_PCT


@dataclass(frozen=True)
class OrderLine:
    sku: str
    qty: int
    discount_pct: Decimal = Decimal("0")


@dataclass
class Order:
    order_id: str
    customer_id: str
    lines: List[OrderLine] = field(default_factory=list)
    currency: Optional[str] = None   # None: use the customer's currency


@dataclass
class InvoiceLine:
    sku: str
    description: str
    qty: int
    amount: Decimal    # net line amount in the invoice currency
    tax: Decimal       # tax on this line in the invoice currency


@dataclass
class Invoice:
    order_id: str
    customer_id: str
    currency: str
    lines: List[InvoiceLine]
    subtotal: Decimal
    tax: Decimal
    total: Decimal

    @property
    def line_count(self):
        return len(self.lines)
