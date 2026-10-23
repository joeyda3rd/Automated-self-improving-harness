"""Product catalog."""
import json

from .currency import check_currency
from .models import Product
from .money import to_decimal

TAX_CLASSES = ("standard", "food", "digital")


class CatalogError(KeyError):
    pass


class Catalog:
    def __init__(self, products=()):
        self._products = {}
        for p in products:
            self.add(p)

    def add(self, product):
        if product.sku in self._products:
            raise CatalogError(f"duplicate sku {product.sku!r}")
        if product.tax_class not in TAX_CLASSES:
            raise CatalogError(f"bad tax class {product.tax_class!r} for {product.sku}")
        check_currency(product.currency)
        self._products[product.sku] = product

    def get(self, sku):
        try:
            return self._products[sku]
        except KeyError:
            raise CatalogError(f"unknown sku {sku!r}") from None

    def __contains__(self, sku):
        return sku in self._products

    def __len__(self):
        return len(self._products)

    def __iter__(self):
        return iter(sorted(self._products.values(), key=lambda p: p.sku))

    @classmethod
    def from_records(cls, records):
        products = []
        for r in records:
            products.append(Product(
                sku=r["sku"],
                name=r.get("name", r["sku"]),
                unit_price=to_decimal(r["unit_price"]),
                currency=r.get("currency", "USD"),
                tax_class=r.get("tax_class", "standard"),
            ))
        return cls(products)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_records(json.load(f))
