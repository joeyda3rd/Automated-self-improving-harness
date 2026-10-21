import unittest

from uwrap import display_width, justify, wrap


class UWrapTest(unittest.TestCase):
    def test_width(self):
        self.assertEqual(display_width("a\tb"), 5)
        self.assertEqual(display_width("\u6f22e\u0301"), 3)

    def test_wrap(self):
        self.assertEqual(wrap("x abcdefghij y", 4), "x\nabcd\nefgh\nij y")
        self.assertEqual(wrap("e\u0301e\u0301e\u0301", 2), "e\u0301e\u0301\ne\u0301")

    def test_justify(self):
        self.assertEqual(justify("ab \u6f22\u5b57 cd \u6f22 x", 8), "ab  \u6f22\u5b57\ncd \u6f22 x")

    def test_bad_width(self):
        for w in (0, True, 2.0):
            with self.assertRaises(ValueError):
                wrap("a", w)


if __name__ == "__main__":
    unittest.main()
