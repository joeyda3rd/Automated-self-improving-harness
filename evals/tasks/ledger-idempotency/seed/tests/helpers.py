import os
import shutil
import tempfile
import unittest


class TempStoreCase(unittest.TestCase):
    """Gives each test a fresh directory and a store path inside it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ledger-test-")
        self.path = os.path.join(self.dir, "events.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
