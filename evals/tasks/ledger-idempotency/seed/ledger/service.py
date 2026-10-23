"""The ledger service: validates events, applies them and persists them."""
from .accounts import AccountBook
from .events import validate_event
from .store import EventStore


class Ledger:
    """A ledger backed by a JSON-lines event store at ``path``.

    Creating a ``Ledger`` on an existing store replays it.
    """

    def __init__(self, path):
        self.store = EventStore(path)
        self.book = AccountBook()
        self.history = []  # applied transfers: (key, source, destination, amount)
        for event in self.store.read():
            self._apply(event)

    # -- writing -------------------------------------------------------------
    def ingest(self, event):
        """Validate, apply and persist one event. Returns ``"applied"``."""
        event = validate_event(event)
        self._apply(event)
        self.store.append(event)
        return "applied"

    def ingest_many(self, events):
        return [self.ingest(e) for e in events]

    def _apply(self, event):
        if event["type"] == "open":
            self.book.open(event["account"], event["limit"])
            return
        source = self.book.get(event["account"])
        source.withdraw(event["amount"])
        destination = self.book.get(event["to"])
        destination.deposit(event["amount"])
        self.history.append((event["key"], event["account"], event["to"], event["amount"]))

    # -- reading -------------------------------------------------------------
    def balance(self, name):
        return self.book.get(name).balance

    def balances(self):
        return self.book.balances()

    def accounts(self):
        return list(self.book)

    def total(self):
        return self.book.total()

    def transfers_for(self, name):
        """Applied transfers touching ``name``, oldest first, as (key, counterparty, signed amount)."""
        out = []
        for key, src, dst, amount in self.history:
            if src == name:
                out.append((key, dst, -amount))
            elif dst == name:
                out.append((key, src, amount))
        return out
