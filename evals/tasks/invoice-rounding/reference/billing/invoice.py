"""Turning orders into invoices.

Each line is computed exactly (discounts, tier discount, conversion) and rounded once;
invoice totals are the sums of the rounded lines.
"""
from decimal import Decimal

from . import pricing
from .currency import check_currency, convert
from .discounts import tier_pct
from .models import Invoice, InvoiceLine
from .money import round_money
from .tax import line_tax


class InvoiceError(ValueError):
    pass


def invoice_currency(order, customer):
    return check_currency(order.currency or customer.currency)


def build_invoice(order, catalog, customers):
    """Build the invoice for `order`."""
    if not order.lines:
        raise InvoiceError(f"order {order.order_id} has no lines")
    customer = customers.get(order.customer_id)
    currency = invoice_currency(order, customer)
    tier = tier_pct(customer.tier)

    lines = []
    for ol in order.lines:
        product = catalog.get(ol.sku)
        net = pricing.line_net(product, ol, tier)
        amount = round_money(convert(net, product.currency, currency), currency)
        lines.append(InvoiceLine(
            sku=product.sku,
            description=product.name,
            qty=ol.qty,
            amount=amount,
            tax=line_tax(amount, customer.region, product.tax_class, currency),
        ))

    subtotal = sum((l.amount for l in lines), Decimal(0))
    tax = sum((l.tax for l in lines), Decimal(0))
    return Invoice(
        order_id=order.order_id,
        customer_id=customer.customer_id,
        currency=currency,
        lines=lines,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
    )


def build_invoices(orders, catalog, customers):
    return [build_invoice(o, catalog, customers) for o in orders]
