"""Command-line entry point: python3 -m taskman [--db PATH] COMMAND [ARGS...]

Exit codes: 0 ok, 1 task error (not found, conflict, invalid value), 2 usage error or unknown command.
"""
import os
import sys

from . import formatting, helpdata, ops
from .clock import today
from .errors import TaskmanError, UsageError
from .parsing import parse_date, parse_id, parse_priority, parse_tags, split_options
from .store import Store

DEFAULT_DB = "tasks.json"


def run_command(store, cmd, args):
    """Execute one command and return its output text."""
    cmd = helpdata.ALIASES.get(cmd, cmd)
    now = today()
    if cmd == "add":
        pos, opts = split_options(args, {"-p": "priority", "-t": "tags", "-d": "due"})
        title = " ".join(pos).strip()
        if not title:
            raise UsageError("usage: add TITLE... [-p PRI] [-t TAGS] [-d DATE]")
        priority = parse_priority(opts["priority"]) if "priority" in opts else "normal"
        tags = parse_tags(opts["tags"]) if "tags" in opts else []
        due = parse_date(opts["due"], now) if "due" in opts else None
        task = ops.add_task(store, title, priority, tags, due)
        return f"added #{task.id}: {task.title}"
    elif cmd == "list":
        pos, opts = split_options(args, {"--tag": "tag", "--sort": "sort"}, {"--all": "all", "-a": "all"})
        if pos:
            raise UsageError("usage: list [--all] [--tag TAG] [--sort KEY]")
        sort = opts.get("sort", "id")
        if sort not in ("id", "pri", "due"):
            raise ValidationError_(f"invalid sort key: {sort} (expected id, pri or due)")
        tag = parse_tags(opts["tag"])[0] if "tag" in opts else None
        tasks = ops.list_tasks(store, include_done=opts.get("all", False), tag=tag, sort=sort)
        return formatting.task_lines(tasks, now)
    elif cmd == "show":
        if len(args) != 1:
            raise UsageError("usage: show ID")
        return formatting.task_detail(store.get(parse_id(args[0])), now)
    elif cmd == "done":
        if not args:
            raise UsageError("usage: done ID...")
        ids = [parse_id(a) for a in args]
        out = []
        for task_id in ids:
            task = ops.complete(store, task_id)
            out.append(f"completed #{task.id}: {task.title}")
        return "\n".join(out)
    elif cmd == "undo":
        if len(args) != 1:
            raise UsageError("usage: undo ID")
        task = ops.reopen(store, parse_id(args[0]))
        return f"reopened #{task.id}: {task.title}"
    elif cmd == "rm":
        if len(args) != 1:
            raise UsageError("usage: rm ID")
        task = ops.delete(store, parse_id(args[0]))
        return f"deleted #{task.id}: {task.title}"
    elif cmd == "rename":
        if len(args) < 2:
            raise UsageError("usage: rename ID TITLE...")
        task_id = parse_id(args[0])
        title = " ".join(args[1:]).strip()
        if not title:
            raise UsageError("usage: rename ID TITLE...")
        old, task = ops.rename(store, task_id, title)
        return f"renamed #{task.id}: {old} -> {task.title}"
    elif cmd == "tag":
        if len(args) != 2:
            raise UsageError("usage: tag ID TAGS")
        task = ops.add_tags(store, parse_id(args[0]), parse_tags(args[1]))
        return formatting.tags_line(task)
    elif cmd == "untag":
        if len(args) != 2:
            raise UsageError("usage: untag ID TAGS")
        task = ops.remove_tags(store, parse_id(args[0]), parse_tags(args[1]))
        return formatting.tags_line(task)
    elif cmd == "pri":
        if len(args) != 2:
            raise UsageError("usage: pri ID PRIORITY")
        task = ops.set_priority(store, parse_id(args[0]), parse_priority(args[1]))
        return f"#{task.id} priority: {task.priority}"
    elif cmd == "due":
        if len(args) != 2:
            raise UsageError("usage: due ID DATE|none")
        task_id = parse_id(args[0])
        due = None if args[1].lower() == "none" else parse_date(args[1], now)
        task = ops.set_due(store, task_id, due)
        return f"#{task.id} due: {task.due or '(none)'}"
    elif cmd == "search":
        query = " ".join(args).strip()
        if not query:
            raise UsageError("usage: search QUERY...")
        return formatting.task_lines(ops.search(store, query), now, empty="no matches")
    elif cmd == "stats":
        if args:
            raise UsageError("usage: stats")
        return formatting.stats_text(ops.stats(store))
    elif cmd == "purge":
        pos, opts = split_options(args, {}, {"--dry-run": "dry_run", "-n": "dry_run"})
        if pos:
            raise UsageError("usage: purge [--dry-run]")
        victims = ops.purge(store, dry_run=opts.get("dry_run", False))
        if not victims:
            return "nothing to purge"
        if opts.get("dry_run"):
            return f"would purge {len(victims)} task(s): " + ", ".join(f"#{t.id}" for t in victims)
        return f"purged {len(victims)} task(s)"
    elif cmd == "export":
        pos, opts = split_options(args, {"--format": "format", "-f": "format"})
        if pos:
            raise UsageError("usage: export [--format csv|json]")
        fmt = opts.get("format", "csv")
        if fmt == "csv":
            return formatting.export_csv(store.all())
        if fmt == "json":
            return formatting.export_json(store.all())
        raise ValidationError_(f"invalid export format: {fmt}")
    elif cmd == "help":
        return formatting.help_text(helpdata.help_entries())
    raise UnknownCommand(cmd)


class UnknownCommand(Exception):
    pass


def ValidationError_(msg):  # noqa: N802 - small helper so branches read like `raise ...`
    from .errors import ValidationError
    return ValidationError(msg)


def main(argv=None, stdout=None, stderr=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    db = os.environ.get("TASKMAN_DB", DEFAULT_DB)
    if argv[:1] == ["--db"]:
        if len(argv) < 2:
            print("error: option --db needs a value", file=stderr)
            return 2
        db, argv = argv[1], argv[2:]
    if not argv:
        print(formatting.help_text(helpdata.help_entries()), file=stdout)
        return 0
    cmd, args = argv[0], argv[1:]
    store = Store(db)
    try:
        out = run_command(store, cmd, args)
    except UnknownCommand:
        print(f"error: unknown command: {cmd} (try 'help')", file=stderr)
        return 2
    except UsageError as e:
        print(f"error: {e.message}", file=stderr)
        return 2
    except TaskmanError as e:
        print(f"error: {e.message}", file=stderr)
        return 1
    if out:
        print(out, file=stdout)
    return 0
