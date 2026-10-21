"""Loading orders from JSON."""
import json

from .models import Order, OrderLine
from .money import to_decimal


class LoadError(ValueError):
    pass


def order_from_record(r):
    try:
        lines = [OrderLine(sku=l["sku"], qty=l["qty"], discount_pct=to_decimal(l.get("discount_pct", "0")))
                 for l in r["lines"]]
        return Order(order_id=r["order_id"], customer_id=r["customer_id"], lines=lines,
                     currency=r.get("currency"))
    except KeyError as e:
        raise LoadError(f"order record missing {e}") from None


def load_orders(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise LoadError("orders file must contain a JSON list")
    return [order_from_record(r) for r in data]
