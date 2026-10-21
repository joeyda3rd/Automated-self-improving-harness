"""Plain-text reports over a ``Ledger``."""
from .money import format_column, format_money


def trial_balance(ledger):
    """One line per account (sorted by name) plus a TOTAL line, which must be 0.00.

    ::

        alice              12.00
        world             -12.00
        TOTAL               0.00
    """
    lines = []
    for name, balance in sorted(ledger.balances().items()):
        lines.append(f"{name:<12}{format_column(balance)}")
    lines.append(f"{'TOTAL':<12}{format_column(ledger.total())}")
    return "\n".join(lines)


def statement(ledger, name):
    """Running statement for one account: ``key  counterparty  amount  running``."""
    running = 0
    lines = [f"Statement for {name}"]
    for key, other, amount in ledger.transfers_for(name):
        running += amount
        lines.append(f"{key:<10}{other:<12}{format_column(amount, 10)}{format_column(running, 12)}")
    lines.append(f"Closing balance {format_money(running)}")
    return "\n".join(lines)


def largest_accounts(ledger, n=3):
    """The ``n`` accounts with the highest balance, ties broken by name. ``world`` is excluded."""
    items = [(b, a) for a, b in ledger.balances().items() if a != "world"]
    items.sort(key=lambda t: (-t[0], t[1]))
    return [(a, b) for b, a in items[:n]]


def overdrawn(ledger):
    """Accounts with a negative balance (excluding ``world``), most negative first."""
    items = [(b, a) for a, b in ledger.balances().items() if a != "world" and b < 0]
    items.sort()
    return [(a, b) for b, a in items]
