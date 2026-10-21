"""Turning orders into invoices."""
from collections import defaultdict
from decimal import Decimal

from . import pricing
from .currency import check_currency, convert
from .discounts import apply_tier_discount
from .models import Invoice, InvoiceLine
from .money import round_money
from .tax import TaxAccumulator, line_tax


class InvoiceError(ValueError):
    pass


def invoice_currency(order, customer):
    return check_currency(order.currency or customer.currency)


def build_invoice(order, catalog, customers):
    """Build the invoice for `order`.

    Line amounts are shown in the invoice currency; the subtotal is converted from
    the per-currency net totals so that each currency is converted only once.
    """
    if not order.lines:
        raise InvoiceError(f"order {order.order_id} has no lines")
    customer = customers.get(order.customer_id)
    currency = invoice_currency(order, customer)

    lines = []
    net_by_currency = defaultdict(Decimal)
    taxes = TaxAccumulator(customer.region)
    for ol in order.lines:
        product = catalog.get(ol.sku)
        net = pricing.line_net(product, ol)
        net_by_currency[product.currency] += net
        amount = round_money(convert(net, product.currency, currency), currency)
        taxes.add(amount, product.tax_class)
        lines.append(InvoiceLine(
            sku=product.sku,
            description=product.name,
            qty=ol.qty,
            amount=amount,
            tax=line_tax(amount, customer.region, product.tax_class),
        ))

    subtotal = Decimal(0)
    for cur, net in sorted(net_by_currency.items()):
        subtotal += round_money(convert(net, cur, currency), currency)
    subtotal = apply_tier_discount(subtotal, customer.tier, currency)
    tax = round_money(taxes.total(), currency)
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
