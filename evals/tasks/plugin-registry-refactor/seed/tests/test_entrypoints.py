import unittest

from tests.helpers import TempDbCase
from taskman.batch import run_batch
from taskman.store import Store
from taskman.web import handle


class TestCli(TempDbCase):
    def test_add_list(self):
        self.assertEqual(self.cli("add", "buy", "milk", "-t", "home"), (0, "added #1: buy milk\n", ""))
        self.assertEqual(self.cli("ls")[1], "#1   [ ] buy milk  #home\n")

    def test_errors(self):
        self.assertEqual(self.cli("done", "4"), (1, "", "error: task #4 not found\n"))
        self.assertEqual(self.cli("frob")[0], 2)


class TestWeb(unittest.TestCase):
    def test_roundtrip(self):
        s = Store()
        r = handle({"method": "POST", "path": "/commands/add", "body": {"args": ["x", "-p", "h"]}}, s)
        self.assertEqual(r, {"status": 200, "body": {"output": "added #1: x", "lines": ["added #1: x"]}})
        r = handle({"method": "POST", "path": "/commands/undo", "body": {"args": ["1"]}}, s)
        self.assertEqual(r["status"], 409)


class TestBatch(unittest.TestCase):
    def test_stops_on_error(self):
        out = run_batch(Store(), ["add a", "done 1", "done 1", "list --all"])
        self.assertEqual(out[-2:], ["! conflict: task #1 is already done", "= 2 ok, 1 failed"])


if __name__ == "__main__":
    unittest.main()
