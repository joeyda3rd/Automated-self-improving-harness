import unittest
from datetime import datetime as D
from cron import next_fire


class T(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(next_fire("*/15 * * * *", D(2024, 1, 1, 10, 7, 30)), D(2024, 1, 1, 10, 15))
        self.assertEqual(next_fire("30 9 * * *", D(2024, 1, 1, 9, 30)), D(2024, 1, 2, 9, 30))

    def test_leap(self):
        self.assertEqual(next_fire("0 0 29 2 *", D(2097, 3, 1)), D(2104, 2, 29))

    def test_or_rule(self):
        self.assertEqual(next_fire("0 0 13 * FRI", D(2024, 1, 1)), D(2024, 1, 5))

    def test_invalid(self):
        for e in ["60 * * * *", "* * * *", "0 0 30 2 *"]:
            with self.assertRaises(ValueError):
                next_fire(e, D(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
