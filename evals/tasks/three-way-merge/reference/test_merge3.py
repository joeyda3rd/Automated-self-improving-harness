import unittest
from merge3 import merge, merge_text


class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(merge(list("abcde"), list("aBcde"), list("abcDe")), (list("aBcDe"), 0))

    def test_adjacent_conflict(self):
        lines, n = merge(list("abcd"), list("aXcd"), list("abYd"))
        self.assertEqual(n, 1)
        self.assertEqual(lines, ["a", "<<<<<<< ours", "X", "c", "||||||| base", "b", "c", "=======",
                                 "b", "Y", ">>>>>>> theirs", "d"])

    def test_merge_style_trims(self):
        lines, n = merge(["x"], ["p", "o", "s"], ["p", "t", "s"], style="merge")
        self.assertEqual(lines, ["p", "<<<<<<< ours", "o", "=======", "t", ">>>>>>> theirs", "s"])

    def test_text(self):
        self.assertEqual(merge_text("a\nb\n", "a\nB\n", "a\nb\n"), ("a\nB\n", 0))
        with self.assertRaises(ValueError):
            merge([], [], [], style="x")


if __name__ == "__main__":
    unittest.main()
