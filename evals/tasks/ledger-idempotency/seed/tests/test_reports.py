from ledger import Ledger, open_event, transfer_event
from ledger.reports import largest_accounts, overdrawn, statement, trial_balance
from tests.helpers import TempStoreCase


class ReportsTest(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.ledger = Ledger(self.path)
        for e in [open_event("o-a", "alice", 1, 0), open_event("o-b", "bob", 1, 500),
                  open_event("o-c", "carol", 1, 0), transfer_event("w-1", "world", 1, "alice", 1200),
                  transfer_event("t-1", "bob", 2, "carol", 300), transfer_event("t-2", "alice", 2, "carol", 200)]:
            self.ledger.ingest(e)

    def test_trial_balance(self):
        self.assertEqual(trial_balance(self.ledger), "\n".join([
            "alice              10.00",
            "bob                -3.00",
            "carol               5.00",
            "world             -12.00",
            "TOTAL               0.00",
        ]))

    def test_statement(self):
        self.assertEqual(statement(self.ledger, "carol"), "\n".join([
            "Statement for carol",
            "t-1       bob               3.00        3.00",
            "t-2       alice             2.00        5.00",
            "Closing balance 5.00",
        ]))

    def test_rankings(self):
        self.assertEqual(largest_accounts(self.ledger, 2), [("alice", 1000), ("carol", 500)])
        self.assertEqual(overdrawn(self.ledger), [("bob", -300)])
