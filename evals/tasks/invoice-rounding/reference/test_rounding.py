import unittest
from decimal import Decimal as D

from billing.catalog import Catalog
from billing.customers import Customers
from billing.invoice import build_invoice
from billing.models import Order, OrderLine


class RoundingTests(unittest.TestCase):
    def test_round_once_half_even_and_totals_are_line_sums(self):
        catalog = Catalog.from_records([
            {"sku": "API", "unit_price": "0.0125", "currency": "EUR", "tax_class": "digital"},
            {"sku": "PEN", "unit_price": "0.125", "currency": "USD"},
        ])
        customers = Customers.from_records([
            {"customer_id": "g", "currency": "USD", "region": "US-CA", "tier": "gold"},
            {"customer_id": "j", "currency": "JPY", "region": "JP"},
        ])
        inv = build_invoice(Order("o", "g", [OrderLine("API", 333, D("10")), OrderLine("PEN", 1)]),
                            catalog, customers)
        # 0.0125*333*0.9*0.95*1.0832 = 3.85504... ; 0.125*0.95 = 0.11875
        self.assertEqual([l.amount for l in inv.lines], [D("3.86"), D("0.12")])
        self.assertEqual(inv.subtotal, sum(l.amount for l in inv.lines))
        self.assertEqual(inv.tax, sum(l.tax for l in inv.lines))
        inv = build_invoice(Order("p", "j", [OrderLine("PEN", 7)]), catalog, customers)
        self.assertEqual(str(inv.lines[0].amount), "130")   # 0.875 * 148.97 = 130.34875
        self.assertEqual(str(inv.lines[0].tax), "13")


if __name__ == "__main__":
    unittest.main()
