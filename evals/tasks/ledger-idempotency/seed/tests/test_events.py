import unittest

from ledger.errors import InvalidEvent
from ledger.events import describe, open_event, transfer_event, validate_event


class EventsTest(unittest.TestCase):
    def test_valid(self):
        e = open_event("k1", "alice", 1, 500)
        self.assertIs(validate_event(e), e)
        t = transfer_event("k2", "alice", 2, "bob", 10)
        self.assertIs(validate_event(t), t)
        self.assertEqual(describe(t), "k2: alice -> bob 10")

    def test_invalid(self):
        bad = [
            None,
            {"type": "close"},
            dict(open_event("k", "alice", 1), extra=1),
            {k: v for k, v in open_event("k", "alice", 1).items() if k != "limit"},
            open_event("", "alice", 1),
            open_event("k", "Alice", 1),
            open_event("k", "alice", 0),
            open_event("k", "alice", True),
            open_event("k", "alice", 1, -1),
            transfer_event("k", "alice", 1, "alice", 5),
            transfer_event("k", "alice", 1, "bob", 0),
            transfer_event("k", "alice", 1, "bob", 1.5),
            transfer_event("k", "alice", 1, "9bob", 1),
        ]
        for event in bad:
            with self.assertRaises(InvalidEvent, msg=repr(event)):
                validate_event(event)


if __name__ == "__main__":
    unittest.main()
