set -e
# canary: the given tests are correct; editing them instead of fixing the code fails the eval
echo "0903add9715a3b3edcac5689e8b5b1b3a8f8b02f638d0ae4c9f8fa836a9aee81  test_billing.py" | sha256sum -c --quiet
timeout 50 python3 - <<'PY'
import random
from decimal import Decimal as D, ROUND_HALF_EVEN

from billing.catalog import Catalog
from billing.customers import Customers
from billing.invoice import build_invoice
from billing.loader import order_from_record

RATES = {
    ("EUR", "USD"): "1.0832", ("USD", "EUR"): "0.9232", ("GBP", "USD"): "1.2645", ("USD", "GBP"): "0.7908",
    ("JPY", "USD"): "0.006712", ("USD", "JPY"): "148.97", ("EUR", "GBP"): "0.8561", ("GBP", "EUR"): "1.1681",
    ("EUR", "JPY"): "161.38", ("JPY", "EUR"): "0.006197", ("GBP", "JPY"): "188.42", ("JPY", "GBP"): "0.005308",
}
MU = {"USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}
TAX = {
    "US-CA": {"standard": "0.0725", "food": "0", "digital": "0.0725"},
    "US-OR": {"standard": "0", "food": "0", "digital": "0"},
    "DE": {"standard": "0.19", "food": "0.07", "digital": "0.19"},
    "UK": {"standard": "0.20", "food": "0", "digital": "0.20"},
    "JP": {"standard": "0.10", "food": "0.08", "digital": "0.10"},
}
TIER = {"standard": "0", "silver": "2.5", "gold": "5", "platinum": "12.5"}

def rnd(x, cur):
    return x.quantize(D(1).scaleb(-MU[cur]), rounding=ROUND_HALF_EVEN)

def expected(order, products, customers):
    c = customers[order["customer_id"]]
    cur = order.get("currency") or c["currency"]
    lines = []
    for l in order["lines"]:
        p = products[l["sku"]]
        net = D(p["unit_price"]) * l["qty"] * (1 - D(l.get("discount_pct", "0")) / 100) * (1 - D(TIER[c["tier"]]) / 100)
        rate = D(1) if p["currency"] == cur else D(RATES[(p["currency"], cur)])
        amount = rnd(net * rate, cur)
        lines.append((amount, rnd(amount * D(TAX[c["region"]][p["tax_class"]]), cur)))
    sub = sum((a for a, _ in lines), D(0)); tax = sum((t for _, t in lines), D(0))
    return cur, lines, sub, tax, sub + tax

def money_ok(x, cur):
    return isinstance(x, D) and x.as_tuple().exponent == -MU[cur]

rng = random.Random(20261021)
curs = list(MU)
prices = {"USD": ["19.99", "0.125", "2.345", "0.0125", "0.004", "7.50", "1.005", "149.00", "0.3333"],
          "EUR": ["9.95", "0.0375", "12.345", "0.215", "1.10", "0.0049", "55.55"],
          "GBP": ["4.99", "0.0625", "3.335", "0.875", "120.00", "0.0101"],
          "JPY": ["1200", "85", "3", "1999", "0.5", "12.5"]}
products = {}
for i in range(60):
    cur = rng.choice(curs)
    products[f"P{i}"] = {"sku": f"P{i}", "name": f"Product {i}", "unit_price": rng.choice(prices[cur]),
                         "currency": cur, "tax_class": rng.choice(["standard", "food", "digital"])}
customers = {}
for i in range(40):
    customers[f"C{i}"] = {"customer_id": f"C{i}", "name": f"Cust {i}", "currency": rng.choice(curs),
                          "region": rng.choice(list(TAX)), "tier": rng.choice(list(TIER))}
catalog = Catalog.from_records(list(products.values()))
registry = Customers.from_records(list(customers.values()))

# hand-picked cases first, then many random ones
orders = [
    {"order_id": "H1", "customer_id": "X1", "lines": [{"sku": "T1", "qty": 1}]},                         # 0.125 -> 0.12
    {"order_id": "H2", "customer_id": "X1", "lines": [{"sku": "T2", "qty": 3, "discount_pct": "50"}]},   # gross 0.0125*3 rounding
    {"order_id": "H3", "customer_id": "X2", "lines": [{"sku": "T3", "qty": 2}, {"sku": "T1", "qty": 4}]},  # JPY tax 0 decimals
    {"order_id": "H4", "customer_id": "X3", "currency": "USD", "lines": [{"sku": "T4", "qty": 1}, {"sku": "T4", "qty": 1}]},
]
for i in range(1500):
    ls = []
    for _ in range(rng.randint(1, 6)):
        l = {"sku": rng.choice(list(products)), "qty": rng.choice([1, 1, 2, 3, 7, 12, 99, 250, 1001])}
        if rng.random() < 0.6:
            l["discount_pct"] = rng.choice(["0", "2.5", "5", "10", "12.5", "15", "33", "33.3"])
        ls.append(l)
    o = {"order_id": f"R{i}", "customer_id": rng.choice(list(customers)), "lines": ls}
    if rng.random() < 0.35:
        o["currency"] = rng.choice(curs)
    orders.append(o)
extra_p = {"T1": {"sku": "T1", "name": "Pen", "unit_price": "0.125", "currency": "USD", "tax_class": "standard"},
           "T2": {"sku": "T2", "name": "Calls", "unit_price": "0.0125", "currency": "USD", "tax_class": "digital"},
           "T3": {"sku": "T3", "name": "Tea", "unit_price": "1235", "currency": "JPY", "tax_class": "standard"},
           "T4": {"sku": "T4", "name": "Scarf", "unit_price": "10.00", "currency": "EUR", "tax_class": "standard"}}
extra_c = {"X1": {"customer_id": "X1", "name": "x1", "currency": "USD", "region": "US-OR", "tier": "standard"},
           "X2": {"customer_id": "X2", "name": "x2", "currency": "JPY", "region": "JP", "tier": "standard"},
           "X3": {"customer_id": "X3", "name": "x3", "currency": "GBP", "region": "UK", "tier": "gold"}}
for k, v in extra_p.items():
    catalog.add(Catalog.from_records([v]).get(k)); products[k] = v
for k, v in extra_c.items():
    registry.add(Customers.from_records([v]).get(k)); customers[k] = v

bad = 0
for o in orders:
    inv = build_invoice(order_from_record(o), catalog, registry)
    cur, lines, sub, tax, total = expected(o, products, customers)
    got = ([(l.amount, l.tax) for l in inv.lines], inv.subtotal, inv.tax, inv.total)
    ok = (inv.currency == cur and got == (lines, sub, tax, total)
          and all(money_ok(x, cur) for l in inv.lines for x in (l.amount, l.tax))
          and all(money_ok(x, cur) for x in (inv.subtotal, inv.tax, inv.total)))
    if not ok:
        bad += 1
        if bad <= 3:
            print(f"order {o['order_id']} ({cur}): got lines={got[0]} subtotal={got[1]!r} tax={got[2]!r} total={got[3]!r}\n"
                  f"   want lines={lines} subtotal={sub!r} tax={tax!r} total={total!r}")
assert bad == 0, f"{bad} of {len(orders)} invoices differ from the policy"
PY
d=$(mktemp -d)
printf '[{"sku":"A","name":"Alpha","unit_price":"0.125","currency":"EUR"}]' > $d/cat.json
printf '[{"customer_id":"c","name":"Cee","currency":"USD","region":"DE","tier":"gold"}]' > $d/cus.json
printf '[{"order_id":"o1","customer_id":"c","lines":[{"sku":"A","qty":3}]}]' > $d/ord.json
python3 -m billing $d/cat.json $d/cus.json $d/ord.json | grep -q '^TOTAL  *0\.46 USD$'
python3 -m unittest -q 2>/dev/null
