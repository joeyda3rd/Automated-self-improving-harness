import json

from ledger.store import EventStore
from tests.helpers import TempStoreCase


class StoreTest(TempStoreCase):
    def test_roundtrip(self):
        store = EventStore(self.path)
        self.assertEqual(store.read(), [])
        store.append({"b": 1, "a": [1, 2]})
        store.append({"x": "y"})
        self.assertEqual(store.read(), [{"a": [1, 2], "b": 1}, {"x": "y"}])
        self.assertEqual(store.count(), 2)

    def test_line_format(self):
        store = EventStore(self.path)
        store.append({"b": 1, "a": 2})
        with open(self.path) as fh:
            self.assertEqual(fh.read(), json.dumps({"a": 2, "b": 1}) + "\n")

    def test_clear(self):
        store = EventStore(self.path)
        store.append({"a": 1})
        store.clear()
        self.assertEqual(store.read(), [])
