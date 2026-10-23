from ledger import GapTooLarge, IdempotencyConflict, Ledger, StaleEvent, open_event, transfer_event
from tests.helpers import TempStoreCase


class IngestionTest(TempStoreCase):
    def test_duplicates_and_conflicts(self):
        ledger = Ledger(self.path)
        self.assertEqual(ledger.ingest(open_event("o", "alice", 1)), "applied")
        self.assertEqual(ledger.ingest(open_event("o", "alice", 1)), "duplicate")
        with self.assertRaises(IdempotencyConflict):
            ledger.ingest(open_event("o", "alice", 1, 5))
        with self.assertRaises(StaleEvent):
            ledger.ingest(open_event("o2", "alice", 1))

    def test_buffering_and_rebuild(self):
        ledger = Ledger(self.path, max_gap=1)
        ledger.ingest(open_event("o", "alice", 1))
        self.assertEqual(ledger.ingest(transfer_event("t3", "world", 2, "alice", 5)), "buffered")
        with self.assertRaises(GapTooLarge):
            ledger.ingest(transfer_event("t4", "world", 3, "alice", 5))
        self.assertEqual(ledger.ingest(transfer_event("t2", "alice", 2, "world", 1)), "rejected")
        self.assertEqual(ledger.ingest(transfer_event("t1", "world", 1, "alice", 5)), "applied")
        snap = ledger.snapshot()
        self.assertEqual(snap["applied"], ["o", "t1", "t3"])
        self.assertEqual(snap["rejected"], [["t2", "overdraft"]])
        self.assertEqual(Ledger(self.path, max_gap=1).snapshot(), snap)
