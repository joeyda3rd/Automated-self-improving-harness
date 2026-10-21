"""Load inventory items from CSV: sku,name,category,qty,unit_cost (with a header row)."""
import csv

from .models import Item


def load_csv(path):
    items = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            items.append(Item(
                sku=row["sku"].strip(),
                name=row["name"].strip(),
                category=row["category"].strip(),
                qty=int(row["qty"]),
                unit_cost=int(row["unit_cost"]),
            ))
    return items
