import unittest

from tests.helpers import TempDbCase
from taskman.registry import CommandConflictError, Registry, registry


class TestRegistry(unittest.TestCase):
    def test_order_and_conflicts(self):
        r = Registry()
        f = lambda store, args: "x"  # noqa: E731
        r.register("b", f, usage="b", summary="b", order=5)
        r.register("a", f, usage="a", summary="a", aliases=("aa",))
        self.assertEqual([c.name for c in r.commands()], ["b", "a"])
        with self.assertRaises(CommandConflictError):
            r.register("c", f, usage="c", summary="c", aliases=("aa",))
        self.assertNotIn("c", r)

    def test_builtins(self):
        self.assertEqual(registry.resolve("later").name, "snooze")


class TestSnooze(TempDbCase):
    def test_snooze(self):
        self.cli("add", "x", "-d", "2026-03-10")
        self.assertEqual(self.cli("snooze", "1", "2"), (0, "#1 due: 2026-03-12 (was 2026-03-10)\n", ""))
        self.assertEqual(self.cli("snooze", "1", "0")[0], 1)


if __name__ == "__main__":
    unittest.main()
