"""Reports over inventory items."""


def total_value(items):
    return round(sum(i.qty * i.unit_cost for i in items), 2)


def low_stock(items, thresholds, default=5):
    low = [i for i in items if i.qty < thresholds.get(i.category, default)]
    return sorted(low, key=lambda i: (i.category, i.qty, i.sku))
