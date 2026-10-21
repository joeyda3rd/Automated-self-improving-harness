import unittest

from ledger.errors import InvalidAmount
from ledger.money import format_column, format_money, parse_money, split_evenly


class MoneyTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_money("12.34"), 1234)
        self.assertEqual(parse_money("7"), 700)
        self.assertEqual(parse_money("-0.5"), -50)
        self.assertEqual(parse_money(" 3.05 "), 305)

    def test_parse_rejects(self):
        for bad in ["", "1.234", "abc", "1,00", None, "--1"]:
            with self.assertRaises(InvalidAmount):
                parse_money(bad)

    def test_format(self):
        self.assertEqual(format_money(1234), "12.34")
        self.assertEqual(format_money(-5), "-0.05")
        self.assertEqual(format_money(0), "0.00")
        self.assertEqual(format_column(100, 6), "  1.00")
        with self.assertRaises(TypeError):
            format_money(1.5)

    def test_split(self):
        self.assertEqual(split_evenly(100, 3), [34, 33, 33])
        self.assertEqual(sum(split_evenly(1001, 7)), 1001)


if __name__ == "__main__":
    unittest.main()
