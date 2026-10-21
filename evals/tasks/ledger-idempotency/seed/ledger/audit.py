"""Consistency checks over a ``Ledger``.

``verify(ledger)`` returns a list of human readable violations (empty when the
ledger is consistent). It is cheap enough to call after every event in tests.
"""
from .accounts import WORLD


def verify(ledger):
    problems = []
    balances = ledger.balances()
    total = sum(balances.values())
    if total != 0:
        problems.append(f"balances sum to {total}, expected 0")
    for name in ledger.accounts():
        account = ledger.book.get(name)
        if account.limit is not None and account.balance < -account.limit:
            problems.append(f"{name}: balance {account.balance} below limit -{account.limit}")
    if WORLD not in balances:
        problems.append("world account missing")
    flows = {}
    for _key, src, dst, amount in ledger.history:
        flows[src] = flows.get(src, 0) - amount
        flows[dst] = flows.get(dst, 0) + amount
    for name, balance in balances.items():
        if flows.get(name, 0) != balance:
            problems.append(f"{name}: balance {balance} does not match history {flows.get(name, 0)}")
    return problems


def assert_consistent(ledger):
    problems = verify(ledger)
    if problems:
        raise AssertionError("; ".join(problems))
