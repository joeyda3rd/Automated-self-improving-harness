"""Customer registry."""
import json

from .currency import check_currency
from .discounts import TIER_DISCOUNT_PCT
from .models import Customer
from .tax import TAX_RATES


class CustomerError(KeyError):
    pass


class Customers:
    def __init__(self, customers=()):
        self._by_id = {}
        for c in customers:
            self.add(c)

    def add(self, customer):
        if customer.customer_id in self._by_id:
            raise CustomerError(f"duplicate customer {customer.customer_id!r}")
        check_currency(customer.currency)
        if customer.region not in TAX_RATES:
            raise CustomerError(f"unknown region {customer.region!r}")
        if customer.tier not in TIER_DISCOUNT_PCT:
            raise CustomerError(f"unknown tier {customer.tier!r}")
        self._by_id[customer.customer_id] = customer

    def get(self, customer_id):
        try:
            return self._by_id[customer_id]
        except KeyError:
            raise CustomerError(f"unknown customer {customer_id!r}") from None

    def __len__(self):
        return len(self._by_id)

    @classmethod
    def from_records(cls, records):
        return cls(Customer(
            customer_id=r["customer_id"],
            name=r.get("name", r["customer_id"]),
            currency=r.get("currency", "USD"),
            region=r["region"],
            tier=r.get("tier", "standard"),
        ) for r in records)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_records(json.load(f))
