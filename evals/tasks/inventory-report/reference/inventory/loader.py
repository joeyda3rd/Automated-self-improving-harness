"""Load inventory items from CSV: sku,name,category,qty,unit_cost (with a header row)."""
import csv

from .models import Item


def load_csv(path):
    items = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("sku") or not row["sku"].strip():
                continue
            items.append(Item(
                sku=row["sku"].strip(),
                name=row["name"].strip(),
                category=row["category"].strip(),
                qty=int(row["qty"]),
                unit_cost=float(row["unit_cost"]),
            ))
    return items
