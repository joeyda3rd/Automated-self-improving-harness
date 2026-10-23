import io
import json
import os

from ledger.cli import main
from tests.helpers import TempStoreCase


class CliTest(TempStoreCase):
    def write_events(self, events):
        path = os.path.join(self.dir, "in.jsonl")
        with open(path, "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
        return path

    def test_ingest_and_balances(self):
        path = self.write_events([
            {"key": "o-a", "type": "open", "account": "alice", "seq": 1, "limit": 0},
            {"key": "w-1", "type": "transfer", "account": "world", "seq": 1, "to": "alice", "amount": 250},
        ])
        out = io.StringIO()
        self.assertEqual(main([self.path, "ingest", path], out), 0)
        self.assertEqual(out.getvalue(), "o-a applied\nw-1 applied\n")
        out = io.StringIO()
        main([self.path, "balances"], out)
        self.assertIn("alice               2.50", out.getvalue())
