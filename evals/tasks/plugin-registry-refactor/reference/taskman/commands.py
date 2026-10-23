"""Built-in commands. Each takes (store, args: list[str]) and returns output text."""
import datetime

from . import formatting, ops
from .clock import today
from .errors import ConflictError, UsageError, ValidationError
from .parsing import parse_date, parse_id, parse_priority, parse_tags, split_options
from .registry import registry

command = registry.command


@command("add", usage="add TITLE... [-p PRI] [-t TAGS] [-d DATE]", summary="create a task", aliases=("new",))
def add(store, args):
    pos, opts = split_options(args, {"-p": "priority", "-t": "tags", "-d": "due"})
    title = " ".join(pos).strip()
    if not title:
        raise UsageError("usage: add TITLE... [-p PRI] [-t TAGS] [-d DATE]")
    priority = parse_priority(opts["priority"]) if "priority" in opts else "normal"
    tags = parse_tags(opts["tags"]) if "tags" in opts else []
    due = parse_date(opts["due"], today()) if "due" in opts else None
    task = ops.add_task(store, title, priority, tags, due)
    return f"added #{task.id}: {task.title}"


@command("list", usage="list [--all] [--tag TAG] [--sort KEY]", summary="list open tasks (--all: include done)",
         aliases=("ls",))
def list_(store, args):
    pos, opts = split_options(args, {"--tag": "tag", "--sort": "sort"}, {"--all": "all", "-a": "all"})
    if pos:
        raise UsageError("usage: list [--all] [--tag TAG] [--sort KEY]")
    sort = opts.get("sort", "id")
    if sort not in ("id", "pri", "due"):
        raise ValidationError(f"invalid sort key: {sort} (expected id, pri or due)")
    tag = parse_tags(opts["tag"])[0] if "tag" in opts else None
    tasks = ops.list_tasks(store, include_done=opts.get("all", False), tag=tag, sort=sort)
    return formatting.task_lines(tasks, today())


@command("show", usage="show ID", summary="show one task in detail")
def show(store, args):
    if len(args) != 1:
        raise UsageError("usage: show ID")
    return formatting.task_detail(store.get(parse_id(args[0])), today())


@command("done", usage="done ID...", summary="mark tasks as done")
def done(store, args):
    if not args:
        raise UsageError("usage: done ID...")
    ids = [parse_id(a) for a in args]
    out = []
    for task_id in ids:
        task = ops.complete(store, task_id)
        out.append(f"completed #{task.id}: {task.title}")
    return "\n".join(out)


@command("undo", usage="undo ID", summary="mark a done task as open again", aliases=("reopen",))
def undo(store, args):
    if len(args) != 1:
        raise UsageError("usage: undo ID")
    task = ops.reopen(store, parse_id(args[0]))
    return f"reopened #{task.id}: {task.title}"


@command("rm", usage="rm ID", summary="delete a task", aliases=("del", "remove"))
def rm(store, args):
    if len(args) != 1:
        raise UsageError("usage: rm ID")
    task = ops.delete(store, parse_id(args[0]))
    return f"deleted #{task.id}: {task.title}"


@command("rename", usage="rename ID TITLE...", summary="change a task's title")
def rename(store, args):
    if len(args) < 2:
        raise UsageError("usage: rename ID TITLE...")
    task_id = parse_id(args[0])
    title = " ".join(args[1:]).strip()
    if not title:
        raise UsageError("usage: rename ID TITLE...")
    old, task = ops.rename(store, task_id, title)
    return f"renamed #{task.id}: {old} -> {task.title}"


@command("tag", usage="tag ID TAGS", summary="add comma-separated tags")
def tag(store, args):
    if len(args) != 2:
        raise UsageError("usage: tag ID TAGS")
    return formatting.tags_line(ops.add_tags(store, parse_id(args[0]), parse_tags(args[1])))


@command("untag", usage="untag ID TAGS", summary="remove comma-separated tags")
def untag(store, args):
    if len(args) != 2:
        raise UsageError("usage: untag ID TAGS")
    return formatting.tags_line(ops.remove_tags(store, parse_id(args[0]), parse_tags(args[1])))


@command("pri", usage="pri ID PRIORITY", summary="set priority (low, normal, high, urgent)", aliases=("priority",))
def pri(store, args):
    if len(args) != 2:
        raise UsageError("usage: pri ID PRIORITY")
    task = ops.set_priority(store, parse_id(args[0]), parse_priority(args[1]))
    return f"#{task.id} priority: {task.priority}"


@command("due", usage="due ID DATE|none", summary="set or clear the due date")
def due(store, args):
    if len(args) != 2:
        raise UsageError("usage: due ID DATE|none")
    task_id = parse_id(args[0])
    value = None if args[1].lower() == "none" else parse_date(args[1], today())
    task = ops.set_due(store, task_id, value)
    return f"#{task.id} due: {task.due or '(none)'}"


@command("snooze", usage="snooze ID [DAYS]", summary="push the due date back by DAYS days (default 1)",
         aliases=("later",))
def snooze(store, args):
    if len(args) not in (1, 2):
        raise UsageError("usage: snooze ID [DAYS]")
    task_id = parse_id(args[0])
    days = 1
    if len(args) == 2:
        if not (args[1].isdigit() and args[1].isascii()) or not 1 <= int(args[1]) <= 365:
            raise ValidationError(f"invalid number of days: {args[1]} (expected 1-365)")
        days = int(args[1])
    task = store.get(task_id)
    if task.done:
        raise ConflictError(f"task #{task_id} is already done")
    if not task.due:
        raise ConflictError(f"task #{task_id} has no due date")
    old = task.due
    task.due = (datetime.date.fromisoformat(old) + datetime.timedelta(days=days)).isoformat()
    store.save()
    return f"#{task.id} due: {task.due} (was {old})"


@command("search", usage="search QUERY...", summary="find tasks by title or tag (#tag: exact tag)", aliases=("find",))
def search(store, args):
    query = " ".join(args).strip()
    if not query:
        raise UsageError("usage: search QUERY...")
    return formatting.task_lines(ops.search(store, query), today(), empty="no matches")


@command("stats", usage="stats", summary="counts by status and priority")
def stats(store, args):
    if args:
        raise UsageError("usage: stats")
    return formatting.stats_text(ops.stats(store))


@command("purge", usage="purge [--dry-run]", summary="delete all done tasks")
def purge(store, args):
    pos, opts = split_options(args, {}, {"--dry-run": "dry_run", "-n": "dry_run"})
    if pos:
        raise UsageError("usage: purge [--dry-run]")
    victims = ops.purge(store, dry_run=opts.get("dry_run", False))
    if not victims:
        return "nothing to purge"
    if opts.get("dry_run"):
        return f"would purge {len(victims)} task(s): " + ", ".join(f"#{t.id}" for t in victims)
    return f"purged {len(victims)} task(s)"


@command("export", usage="export [--format csv|json]", summary="print all tasks as CSV or JSON")
def export(store, args):
    pos, opts = split_options(args, {"--format": "format", "-f": "format"})
    if pos:
        raise UsageError("usage: export [--format csv|json]")
    fmt = opts.get("format", "csv")
    if fmt == "csv":
        return formatting.export_csv(store.all())
    if fmt == "json":
        return formatting.export_json(store.all())
    raise ValidationError(f"invalid export format: {fmt}")


def help_text():
    return formatting.help_text([(c.usage, c.summary, c.aliases) for c in registry.commands()])


@command("help", usage="help", summary="show this help", aliases=("?",), order=900)
def help_(store, args):
    return help_text()
