"""The ledger service: deduplicates, orders, applies and persists events."""
from .accounts import AccountBook
from .errors import (CorruptStore, GapTooLarge, IdempotencyConflict, LedgerError, SequenceConflict,
                     StaleEvent)
from .events import validate_event
from .store import EventStore


class Ledger:
    """A ledger backed by a JSON-lines event store at ``path``.

    Creating a ``Ledger`` on an existing store rebuilds it.
    """

    def __init__(self, path, max_gap=8):
        if not isinstance(max_gap, int) or isinstance(max_gap, bool) or max_gap < 0:
            raise ValueError("max_gap must be an int >= 0")
        self.store = EventStore(path)
        self.max_gap = max_gap
        self.rebuild()

    def _reset(self):
        self.book = AccountBook()
        self.history = []  # applied transfers: (key, source, destination, amount)
        self.seen = {}  # key -> event, for every applied, rejected or buffered event
        self.last_seq = {}
        self.pending = {}  # account -> {seq: event}
        self.applied = []
        self.rejected = []

    def rebuild(self):
        """Reset and replay every stored event through the ingestion rules."""
        records = self.store.read(repair=True)
        self._reset()
        for n, event in enumerate(records, 1):
            try:
                self._ingest(event, persist=False)
            except LedgerError as exc:
                raise CorruptStore(f"{self.store.path}: line {n}: {type(exc).__name__}: {exc}") from None

    # -- writing -------------------------------------------------------------
    def ingest(self, event):
        """Ingest one event; returns "applied", "rejected", "buffered" or "duplicate"."""
        return self._ingest(event, persist=True)

    def ingest_many(self, events):
        return [self.ingest(e) for e in events]

    def _ingest(self, event, persist):
        event = validate_event(event)
        key, account, seq = event["key"], event["account"], event["seq"]
        if key in self.seen:
            if self.seen[key] == event:
                return "duplicate"
            raise IdempotencyConflict(key)
        last = self.last_seq.get(account, 0)
        if seq <= last:
            raise StaleEvent(f"{key}: {account} seq {seq} <= {last}")
        waiting = self.pending.get(account, {})
        if seq in waiting:
            raise SequenceConflict(f"{key}: {account} seq {seq} already buffered")
        if seq - last - 1 > self.max_gap:
            raise GapTooLarge(f"{key}: {account} seq {seq}, last {last}")
        if persist:
            self.store.append(event)
        self.seen[key] = event
        if seq > last + 1:
            self.pending.setdefault(account, {})[seq] = event
            return "buffered"
        status = self._process(event)
        while self.last_seq[account] + 1 in waiting:
            self._process(waiting.pop(self.last_seq[account] + 1))
        if account in self.pending and not waiting:
            del self.pending[account]
        return status

    def _process(self, event):
        key, account = event["key"], event["account"]
        self.last_seq[account] = event["seq"]
        if event["type"] == "open":
            if account in self.book:
                return self._reject(key, "already_open")
            self.book.open(account, event["limit"])
        else:
            if account not in self.book or event["to"] not in self.book:
                return self._reject(key, "unknown_account")
            source, destination = self.book.get(account), self.book.get(event["to"])
            if not source.can_withdraw(event["amount"]):
                return self._reject(key, "overdraft")
            source.withdraw(event["amount"])
            destination.deposit(event["amount"])
            self.history.append((key, account, event["to"], event["amount"]))
        self.applied.append(key)
        return "applied"

    def _reject(self, key, reason):
        self.rejected.append([key, reason])
        return "rejected"

    # -- reading -------------------------------------------------------------
    def snapshot(self):
        return {
            "accounts": {name: self.book.get(name).as_dict() for name in self.book},
            "last_seq": {a: s for a, s in sorted(self.last_seq.items()) if s > 0},
            "pending": {a: sorted(w) for a, w in sorted(self.pending.items()) if w},
            "applied": list(self.applied),
            "rejected": [list(r) for r in self.rejected],
        }

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
