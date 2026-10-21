import unittest

from tests.helpers import TempDbCase
from taskman import ops
from taskman.errors import ConflictError, NotFoundError
from taskman.store import Store


class TestOps(TempDbCase):
    def test_add_and_persist(self):
        s = Store(self.db)
        t = ops.add_task(s, "write report", "high", ["work"], "2026-03-12")
        self.assertEqual(t.id, 1)
        s2 = Store(self.db)
        self.assertEqual(s2.get(1).title, "write report")
        self.assertEqual(s2.get(1).created, "2026-03-10")

    def test_complete_twice(self):
        s = Store()
        ops.add_task(s, "a")
        ops.complete(s, 1)
        with self.assertRaises(ConflictError):
            ops.complete(s, 1)

    def test_missing(self):
        with self.assertRaises(NotFoundError):
            ops.delete(Store(), 3)

    def test_sort(self):
        s = Store()
        ops.add_task(s, "a", "low")
        ops.add_task(s, "b", "urgent", due="2026-04-01")
        ops.add_task(s, "c", due="2026-03-11")
        self.assertEqual([t.id for t in ops.list_tasks(s, sort="pri")], [2, 3, 1])
        self.assertEqual([t.id for t in ops.list_tasks(s, sort="due")], [3, 2, 1])


if __name__ == "__main__":
    unittest.main()
