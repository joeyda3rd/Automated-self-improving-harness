"""python3 -m billing CATALOG CUSTOMERS ORDERS [--statements]"""
import argparse
import sys

from .catalog import Catalog
from .customers import Customers
from .invoice import build_invoices
from .loader import load_orders
from .render import render_invoice
from .statements import statements_for


def main(argv=None):
    ap = argparse.ArgumentParser(prog="billing")
    ap.add_argument("catalog")
    ap.add_argument("customers")
    ap.add_argument("orders")
    ap.add_argument("--statements", action="store_true")
    args = ap.parse_args(argv)
    catalog, customers = Catalog.load(args.catalog), Customers.load(args.customers)
    invoices = build_invoices(load_orders(args.orders), catalog, customers)
    if args.statements:
        print("\n\n".join(s.render() for s in statements_for(invoices, customers)))
    else:
        print("\n\n".join(render_invoice(i, customers.get(i.customer_id)) for i in invoices))
    return 0


if __name__ == "__main__":
    sys.exit(main())
