import io
import os
import tempfile
import unittest

os.environ["TASKMAN_TODAY"] = "2026-03-10"


class TempDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "tasks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        from taskman.cli import main
        out, err = io.StringIO(), io.StringIO()
        code = main(["--db", self.db, *argv], stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()
