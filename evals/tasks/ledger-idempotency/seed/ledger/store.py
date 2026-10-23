"""Append-only JSON-lines event store.

Each record is written as one line: ``json.dumps(record, sort_keys=True)``
followed by ``"\\n"``, in a single ``write`` call, then flushed and fsynced.
"""
import json
import os


class EventStore:
    def __init__(self, path):
        self.path = path

    def exists(self):
        return os.path.exists(self.path)

    def append(self, record):
        line = json.dumps(record, sort_keys=True) + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def read(self):
        """Return every record in the store, oldest first."""
        if not self.exists():
            return []
        records = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                records.append(json.loads(line))
        return records

    def count(self):
        return len(self.read())

    def clear(self):
        """Remove every record (used by tests and the ``reset`` CLI command)."""
        with open(self.path, "w", encoding="utf-8"):
            pass
