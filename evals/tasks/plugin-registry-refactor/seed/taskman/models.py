"""The Task record."""
from dataclasses import dataclass, field

PRIORITIES = ("low", "normal", "high", "urgent")
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: str = "normal"
    tags: list = field(default_factory=list)
    due: str = None        # ISO date or None
    created: str = ""      # ISO date

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "priority": self.priority,
            "tags": list(self.tags),
            "due": self.due,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=int(d["id"]),
            title=d["title"],
            done=bool(d.get("done", False)),
            priority=d.get("priority", "normal"),
            tags=list(d.get("tags", [])),
            due=d.get("due"),
            created=d.get("created", ""),
        )
