"""Plain-text invoice rendering."""
from .money import format_money

WIDTH = 60


def render_invoice(invoice, customer):
    cur = invoice.currency
    out = [
        f"INVOICE {invoice.order_id}".ljust(WIDTH - 20) + f"{customer.name:>20}",
        "-" * WIDTH,
    ]
    for line in invoice.lines:
        desc = f"{line.qty} x {line.description}"
        if len(desc) > 30:
            desc = desc[:27] + "..."
        out.append(f"{desc:<30}{format_money(line.amount, cur):>15}{format_money(line.tax, cur):>15}")
    out.append("-" * WIDTH)
    out.append(f"{'Subtotal':<30}{format_money(invoice.subtotal, cur):>30}")
    out.append(f"{'Tax':<30}{format_money(invoice.tax, cur):>30}")
    out.append(f"{'TOTAL':<30}{format_money(invoice.total, cur):>30}")
    return "\n".join(out)
