"""File-backed task queue: one JSON file per task in <project>/.ash/tasks/."""
import glob
import os
import time

from .config import load_json, save_json

PENDING, ACTIVE, DONE, FAILED, BLOCKED = "pending", "active", "done", "failed", "blocked"


class TaskStore:
    def __init__(self, project):
        self.project = project
        self.dir = project.tasks_dir

    def path(self, task_id):
        return os.path.join(self.dir, f"{task_id}.json")

    def all(self):
        tasks = [load_json(p) for p in sorted(glob.glob(os.path.join(self.dir, "T-*.json")))]
        return [t for t in tasks if t]

    def get(self, task_id):
        return load_json(self.path(task_id))

    def save(self, task):
        task["updated"] = time.time()
        save_json(self.path(task["id"]), task)
        return task

    def next_id(self):
        nums = [int(t["id"].split("-")[1]) for t in self.all()]
        return f"T-{(max(nums) + 1 if nums else 1):04d}"

    def add(self, title, spec="", kind="build", acceptance=None, depends_on=None,
            priority=3, parent=None, source="cli"):
        task = {
            "id": self.next_id(),
            "kind": kind,
            "title": title.strip(),
            "spec": spec.strip(),
            "acceptance": list(acceptance or []),
            "depends_on": list(depends_on or []),
            "priority": int(priority),
            "parent": parent,
            "source": source,
            "status": PENDING,
            "runs": 0,
            "history": [],
            "created": time.time(),
        }
        return self.save(task)

    def ready(self):
        """Pending tasks whose dependencies are done, best first (priority, then age)."""
        tasks = self.all()
        status = {t["id"]: t["status"] for t in tasks}
        ready = [t for t in tasks if t["status"] == PENDING
                 and all(status.get(d) == DONE for d in t.get("depends_on", []))]
        return sorted(ready, key=lambda t: (t.get("priority", 3), t["created"]))

    def stuck(self):
        """Pending tasks that can never run because a dependency failed or is blocked."""
        tasks = self.all()
        status = {t["id"]: t["status"] for t in tasks}
        return [t for t in tasks if t["status"] == PENDING
                and any(status.get(d) in (FAILED, BLOCKED) for d in t.get("depends_on", []))]

    def counts(self):
        out = {}
        for t in self.all():
            out[t["status"]] = out.get(t["status"], 0) + 1
        return out

    def recover(self):
        """A crash can leave tasks active; put them back in the queue."""
        for t in self.all():
            if t["status"] == ACTIVE:
                t["status"] = PENDING
                t["history"].append({"ts": time.time(), "event": "recovered after interrupted run"})
                self.save(t)


def card(task):
    """The task as the builder sees it."""
    lines = [f"# {task['id']}: {task['title']}", "", task.get("spec") or "(no further spec)"]
    if task.get("acceptance"):
        lines += ["", "## Acceptance criteria"] + [f"- {a}" for a in task["acceptance"]]
    failures = [h for h in task.get("history", []) if h.get("event") == "run" and h.get("outcome") != DONE]
    if failures:
        lines += ["", "## Earlier attempts (learn from them)"]
        lines += [f"- run {i + 1}: {h.get('outcome')}: {h.get('note', '')[:600]}" for i, h in enumerate(failures[-3:])]
    return "\n".join(lines)
