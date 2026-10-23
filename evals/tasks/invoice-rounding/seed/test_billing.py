import json
import os
import tempfile
import unittest
from decimal import Decimal as D

from billing.catalog import Catalog, CatalogError
from billing.currency import CurrencyError, convert
from billing.customers import CustomerError, Customers
from billing.invoice import InvoiceError, build_invoice
from billing.loader import LoadError, load_orders, order_from_record
from billing.models import Order, OrderLine
from billing.money import format_money, round_money
from billing.pricing import PricingError
from billing.render import render_invoice
from billing.statements import statements_for

CATALOG = [
    {"sku": "WID", "name": "Widget", "unit_price": "10.00", "currency": "USD"},
    {"sku": "BOOK", "name": "Cookbook", "unit_price": "12.50", "currency": "USD", "tax_class": "food"},
    {"sku": "TEA", "name": "Matcha tin", "unit_price": "1200", "currency": "JPY", "tax_class": "standard"},
]
CUSTOMERS = [
    {"customer_id": "c1", "name": "Acme Corp", "currency": "USD", "region": "US-CA"},
    {"customer_id": "c2", "name": "Kyoto Tea", "currency": "JPY", "region": "JP"},
]


def setup():
    return Catalog.from_records(CATALOG), Customers.from_records(CUSTOMERS)


class InvoiceTests(unittest.TestCase):
    def test_simple_usd_invoice(self):
        catalog, customers = setup()
        order = Order("A-1", "c1", [OrderLine("WID", 3, D("10")), OrderLine("BOOK", 2)])
        inv = build_invoice(order, catalog, customers)
        self.assertEqual(inv.currency, "USD")
        self.assertEqual([l.amount for l in inv.lines], [D("27.00"), D("25.00")])
        self.assertEqual([l.tax for l in inv.lines], [D("1.96"), D("0.00")])
        self.assertEqual((str(inv.subtotal), str(inv.tax), str(inv.total)), ("52.00", "1.96", "53.96"))

    def test_single_currency_jpy(self):
        catalog, customers = setup()
        inv = build_invoice(Order("J-1", "c2", [OrderLine("TEA", 2)]), catalog, customers)
        self.assertEqual(inv.lines[0].amount, D("2400"))
        self.assertEqual(inv.lines[0].tax, D("240"))
        self.assertEqual(inv.total, D("2640"))

    def test_errors(self):
        catalog, customers = setup()
        with self.assertRaises(InvoiceError):
            build_invoice(Order("E-1", "c1", []), catalog, customers)
        with self.assertRaises(CatalogError):
            build_invoice(Order("E-2", "c1", [OrderLine("NOPE", 1)]), catalog, customers)
        with self.assertRaises(CustomerError):
            build_invoice(Order("E-3", "zz", [OrderLine("WID", 1)]), catalog, customers)
        with self.assertRaises(PricingError):
            build_invoice(Order("E-4", "c1", [OrderLine("WID", 0)]), catalog, customers)
        with self.assertRaises(CurrencyError):
            build_invoice(Order("E-5", "c1", [OrderLine("WID", 1)], currency="CHF"), catalog, customers)

    def test_render(self):
        catalog, customers = setup()
        order = Order("A-1", "c1", [OrderLine("WID", 3, D("10")), OrderLine("BOOK", 2)])
        text = render_invoice(build_invoice(order, catalog, customers), customers.get("c1"))
        self.assertEqual(text.splitlines(), [
            "INVOICE A-1                                        Acme Corp",
            "------------------------------------------------------------",
            "3 x Widget                          27.00 USD       1.96 USD",
            "2 x Cookbook                        25.00 USD       0.00 USD",
            "------------------------------------------------------------",
            "Subtotal                                           52.00 USD",
            "Tax                                                 1.96 USD",
            "TOTAL                                              53.96 USD",
        ])


class MoneyTests(unittest.TestCase):
    def test_round_and_format(self):
        self.assertEqual(round_money(D("2.346"), "USD"), D("2.35"))
        self.assertEqual(str(round_money(D("1234.6"), "JPY")), "1235")
        self.assertEqual(format_money(D("1234.5"), "EUR"), "1,234.50 EUR")
        self.assertEqual(format_money(D("-5"), "GBP"), "-5.00 GBP")
        self.assertEqual(format_money(D("98765"), "JPY"), "98,765 JPY")

    def test_convert_same_currency(self):
        self.assertEqual(convert(D("100.00"), "USD", "USD"), D("100.00"))
        with self.assertRaises(CurrencyError):
            convert(D("1"), "USD", "XXX")


class LoaderTests(unittest.TestCase):
    def test_load_orders(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "orders.json")
            with open(p, "w") as f:
                json.dump([{"order_id": "o1", "customer_id": "c1",
                            "lines": [{"sku": "WID", "qty": 2, "discount_pct": "12.5"}]}], f)
            (order,) = load_orders(p)
        self.assertEqual(order.lines[0].discount_pct, D("12.5"))
        self.assertIsNone(order.currency)
        with self.assertRaises(LoadError):
            order_from_record({"order_id": "x"})

    def test_registry_validation(self):
        with self.assertRaises(CatalogError):
            Catalog.from_records(CATALOG + [CATALOG[0]])
        with self.assertRaises(CustomerError):
            Customers.from_records([{"customer_id": "x", "region": "MARS"}])


class StatementTests(unittest.TestCase):
    def test_statement_totals(self):
        catalog, customers = setup()
        invs = [build_invoice(Order(f"S-{i}", "c1", [OrderLine("WID", i)]), catalog, customers)
                for i in (2, 4)]
        invs.append(build_invoice(Order("S-3", "c1", [OrderLine("TEA", 1)], currency="JPY"),
                                  catalog, customers))
        (st,) = statements_for(invs, customers)
        totals = st.totals()
        self.assertEqual(list(totals), ["USD", "JPY"])
        self.assertEqual(totals["USD"], D("64.35"))
        self.assertIn("TOTAL USD", st.render())


if __name__ == "__main__":
    unittest.main()
