"""Reports over inventory items."""


def total_value(items):
    return round(sum(i.qty * i.unit_cost for i in items), 2)
