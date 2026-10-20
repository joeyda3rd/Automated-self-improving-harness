"""A tiny todo list stored in todo.json.

Usage:
  python3 todo.py add "text"
  python3 todo.py list
"""
import json
import os
import sys

DB = os.environ.get("TODO_DB", "todo.json")


def load():
    if not os.path.exists(DB):
        return []
    with open(DB) as fh:
        return json.load(fh)


def save(items):
    with open(DB, "w") as fh:
        json.dump(items, fh)


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    items = load()
    if argv[0] == "add" and len(argv) == 2:
        items.append({"id": len(items) + 1, "text": argv[1], "done": False})
        save(items)
        print(items[-1]["id"])
        return 0
    if argv[0] == "list":
        for item in items:
            print(f"{item['id']}. [{'x' if item['done'] else ' '}] {item['text']}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
