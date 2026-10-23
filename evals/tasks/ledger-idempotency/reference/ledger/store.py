"""Append-only JSON-lines event store.

Each record is written as one line: ``json.dumps(record, sort_keys=True)``
followed by ``"\\n"``, in a single ``write`` call, then flushed and fsynced.
"""
import json
import os

from .errors import CorruptStore


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

    def read(self, repair=False):
        """Return every record in the store, oldest first.

        An unterminated last line is an interrupted write: it is ignored, and with
        ``repair=True`` cut off the file. Any complete line that is not a JSON
        object raises ``CorruptStore``.
        """
        if not self.exists():
            return []
        with open(self.path, "rb") as fh:
            data = fh.read()
        end = data.rfind(b"\n") + 1
        if end < len(data) and repair:
            with open(self.path, "r+b") as fh:
                fh.truncate(end)
        records = []
        for n, line in enumerate(data[:end].split(b"\n")[:-1], 1):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise CorruptStore(f"{self.path}: line {n} is not JSON") from None
            if not isinstance(record, dict):
                raise CorruptStore(f"{self.path}: line {n} is not an object")
            records.append(record)
        return records

    def count(self):
        return len(self.read())

    def clear(self):
        """Remove every record (used by tests and the ``reset`` CLI command)."""
        with open(self.path, "w", encoding="utf-8"):
            pass
