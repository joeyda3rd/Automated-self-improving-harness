from ledger import Ledger, open_event, transfer_event
from ledger.errors import InvalidEvent
from tests.helpers import TempStoreCase


def opening(ledger):
    ledger.ingest(open_event("o-a", "alice", 1, 0))
    ledger.ingest(open_event("o-b", "bob", 1, 1000))
    ledger.ingest(transfer_event("w-1", "world", 1, "alice", 5000))


class ServiceTest(TempStoreCase):
    def test_open_and_transfer(self):
        ledger = Ledger(self.path)
        opening(ledger)
        self.assertEqual(ledger.ingest(transfer_event("t-1", "alice", 2, "bob", 1200)), "applied")
        self.assertEqual(ledger.balances(), {"alice": 3800, "bob": 1200, "world": -5000})
        self.assertEqual(ledger.total(), 0)

    def test_overdraft_within_limit(self):
        ledger = Ledger(self.path)
        opening(ledger)
        ledger.ingest(transfer_event("t-1", "bob", 2, "alice", 1000))
        self.assertEqual(ledger.balance("bob"), -1000)

    def test_invalid_event_not_stored(self):
        ledger = Ledger(self.path)
        with self.assertRaises(InvalidEvent):
            ledger.ingest({"type": "open"})
        self.assertEqual(ledger.store.count(), 0)

    def test_reopen_replays_store(self):
        ledger = Ledger(self.path)
        opening(ledger)
        ledger.ingest(transfer_event("t-1", "alice", 2, "bob", 700))
        again = Ledger(self.path)
        self.assertEqual(again.balances(), ledger.balances())
        self.assertEqual(again.transfers_for("bob"), [("t-1", "alice", 700)])

    def test_transfers_for(self):
        ledger = Ledger(self.path)
        opening(ledger)
        ledger.ingest(transfer_event("t-1", "alice", 2, "bob", 100))
        ledger.ingest(transfer_event("t-2", "bob", 2, "alice", 40))
        self.assertEqual(ledger.transfers_for("alice"),
                         [("w-1", "world", 5000), ("t-1", "bob", -100), ("t-2", "bob", 40)])


class AuditTest(TempStoreCase):
    def test_consistent(self):
        from ledger.audit import verify
        ledger = Ledger(self.path)
        opening(ledger)
        ledger.ingest(transfer_event("t-1", "alice", 2, "bob", 10))
        self.assertEqual(verify(ledger), [])
        ledger.book.get("bob").balance += 1
        self.assertEqual(len(verify(ledger)), 2)
