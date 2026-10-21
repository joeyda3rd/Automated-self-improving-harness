"""Command list shown by `help` and GET /commands: (name, usage, summary, aliases), in display order."""

COMMANDS = [
    ("add", "add TITLE... [-p PRI] [-t TAGS] [-d DATE]", "create a task", ("new",)),
    ("list", "list [--all] [--tag TAG] [--sort KEY]", "list open tasks (--all: include done)", ("ls",)),
    ("show", "show ID", "show one task in detail", ()),
    ("done", "done ID...", "mark tasks as done", ()),
    ("undo", "undo ID", "mark a done task as open again", ("reopen",)),
    ("rm", "rm ID", "delete a task", ("del", "remove")),
    ("rename", "rename ID TITLE...", "change a task's title", ()),
    ("tag", "tag ID TAGS", "add comma-separated tags", ()),
    ("untag", "untag ID TAGS", "remove comma-separated tags", ()),
    ("pri", "pri ID PRIORITY", "set priority (low, normal, high, urgent)", ("priority",)),
    ("due", "due ID DATE|none", "set or clear the due date", ()),
    ("search", "search QUERY...", "find tasks by title or tag (#tag: exact tag)", ("find",)),
    ("stats", "stats", "counts by status and priority", ()),
    ("purge", "purge [--dry-run]", "delete all done tasks", ()),
    ("export", "export [--format csv|json]", "print all tasks as CSV or JSON", ()),
    ("help", "help", "show this help", ("?",)),
]

ALIASES = {alias: name for name, _, _, aliases in COMMANDS for alias in aliases}


def help_entries():
    return [(usage, summary, aliases) for _, usage, summary, aliases in COMMANDS]
