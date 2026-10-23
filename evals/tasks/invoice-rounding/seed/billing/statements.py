"""Customer statements: all invoices of a customer, with totals per currency."""
from collections import OrderedDict
from decimal import Decimal

from .money import format_money


class Statement:
    def __init__(self, customer):
        self.customer = customer
        self.invoices = []

    def add(self, invoice):
        if invoice.customer_id != self.customer.customer_id:
            raise ValueError("invoice belongs to another customer")
        self.invoices.append(invoice)

    def totals(self):
        """Total owed per currency, in order of first appearance."""
        out = OrderedDict()
        for inv in self.invoices:
            out[inv.currency] = out.get(inv.currency, Decimal(0)) + inv.total
        return out

    def render(self):
        lines = [f"Statement for {self.customer.name} ({self.customer.customer_id})"]
        for inv in self.invoices:
            lines.append(f"  {inv.order_id:<12} {format_money(inv.total, inv.currency):>18}")
        for cur, amount in self.totals().items():
            lines.append(f"  {'TOTAL ' + cur:<12} {format_money(amount, cur):>18}")
        return "\n".join(lines)


def statements_for(invoices, customers):
    by_customer = OrderedDict()
    for inv in invoices:
        st = by_customer.get(inv.customer_id)
        if st is None:
            st = by_customer[inv.customer_id] = Statement(customers.get(inv.customer_id))
        st.add(inv)
    return list(by_customer.values())
