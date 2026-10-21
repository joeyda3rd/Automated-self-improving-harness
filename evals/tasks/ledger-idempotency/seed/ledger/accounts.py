"""Accounts and the account book.

The ledger is double-entry: money only moves between accounts, so the sum of
all balances is always zero. Money enters the system from the ``world``
account, which is open from the start and has no overdraft limit.
"""
from .errors import AccountExists, InsufficientFunds, UnknownAccount

WORLD = "world"


class Account:
    __slots__ = ("name", "balance", "limit")

    def __init__(self, name, limit):
        self.name = name
        self.balance = 0
        self.limit = limit  # None means unlimited overdraft

    def can_withdraw(self, amount):
        return self.limit is None or self.balance - amount >= -self.limit

    def withdraw(self, amount):
        if not self.can_withdraw(amount):
            raise InsufficientFunds(f"{self.name}: balance {self.balance}, limit {self.limit}, amount {amount}")
        self.balance -= amount

    def deposit(self, amount):
        self.balance += amount

    def as_dict(self):
        return {"balance": self.balance, "limit": self.limit}

    def __repr__(self):
        return f"Account({self.name!r}, balance={self.balance}, limit={self.limit})"


class AccountBook:
    def __init__(self):
        self._accounts = {WORLD: Account(WORLD, None)}

    def __contains__(self, name):
        return name in self._accounts

    def __iter__(self):
        return iter(sorted(self._accounts))

    def __len__(self):
        return len(self._accounts)

    def open(self, name, limit):
        if name in self._accounts:
            raise AccountExists(name)
        account = Account(name, limit)
        self._accounts[name] = account
        return account

    def get(self, name):
        try:
            return self._accounts[name]
        except KeyError:
            raise UnknownAccount(name) from None

    def balances(self):
        return {name: self._accounts[name].balance for name in self}

    def total(self):
        return sum(a.balance for a in self._accounts.values())
