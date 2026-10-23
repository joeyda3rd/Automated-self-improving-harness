"""JSON-file persistence. A Store with path=None lives in memory only."""
import json
import os

from .errors import NotFoundError
from .models import Task


class Store:
    def __init__(self, path=None):
        self.path = path
        self.tasks = {}
        self.next_id = 1
        if path and os.path.exists(path):
            self.load()

    def load(self):
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.next_id = int(data.get("next_id", 1))
        self.tasks = {}
        for d in data.get("tasks", []):
            t = Task.from_dict(d)
            self.tasks[t.id] = t
        if self.tasks:
            self.next_id = max(self.next_id, max(self.tasks) + 1)

    def save(self):
        if not self.path:
            return
        data = {"next_id": self.next_id, "tasks": [t.to_dict() for t in self.all()]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)

    def all(self):
        return [self.tasks[k] for k in sorted(self.tasks)]

    def get(self, task_id):
        try:
            return self.tasks[task_id]
        except KeyError:
            raise NotFoundError(f"task #{task_id} not found") from None

    def insert(self, task):
        task.id = self.next_id
        self.next_id += 1
        self.tasks[task.id] = task
        return task

    def remove(self, task_id):
        task = self.get(task_id)
        del self.tasks[task_id]
        return task
