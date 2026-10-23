import os
import tempfile
import unittest

from csvq import QueryError, run


class T(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.d = tempfile.TemporaryDirectory()
        os.chdir(self.d.name)
        with open("t.csv", "w") as f:
            f.write("name,qty\na,3\nb,\na,4\n")

    def tearDown(self):
        os.chdir(self.old)
        self.d.cleanup()

    def test_example(self):
        self.assertEqual(run("select name, sum(qty) from t.csv group by name order by SUM(qty) desc"),
                         "name,SUM(qty)\na,7\nb,\n")

    def test_null_where(self):
        self.assertEqual(run("SELECT name FROM t.csv WHERE NOT qty = 3"), "name\na\n")
        self.assertEqual(run("SELECT COUNT(*), COUNT(qty), AVG(qty) FROM t.csv"),
                         "COUNT(*),COUNT(qty),AVG(qty)\n3,2,3.5\n")

    def test_errors(self):
        for q in ["SELECT nope FROM t.csv", "SELECT name FROM t.csv WHERE qty = 'x'",
                  "SELECT name, COUNT(*) FROM t.csv", "SELECT * FROM t.csv LIMIT"]:
            with self.assertRaises(QueryError):
                run(q)


if __name__ == "__main__":
    unittest.main()
