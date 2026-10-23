"""HTTP-style entry point: handle(request, store) -> response.

request:  {"method": "GET" | "POST", "path": str, "body": dict or None}
response: {"status": int, "body": dict}

Routes:
  GET  /commands         list the available commands
  POST /commands/<name>  run a command; body {"args": [str, ...]}
"""
from . import formatting, helpdata, ops
from .clock import today
from .errors import TaskmanError, UsageError, ValidationError
from .parsing import parse_date, parse_id, parse_priority, parse_tags, split_options

STATUS = {"usage": 400, "validation": 400, "not_found": 404, "conflict": 409}
PREFIX = "/commands/"


def _dispatch(store, cmd, args):
    # NOTE: keep in sync with cli.run_command and batch._execute
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
            raise ValidationError(f"invalid sort key: {sort} (expected id, pri or due)")
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
        raise ValidationError(f"invalid export format: {fmt}")
    elif cmd == "help":
        return formatting.help_text(helpdata.help_entries())
    return None



def _error(status, message, kind=None):
    body = {"error": message}
    if kind:
        body["kind"] = kind
    return {"status": status, "body": body}


def handle(request, store):
    method = (request.get("method") or "GET").upper()
    path = request.get("path") or "/"
    if path == "/commands":
        if method != "GET":
            return _error(405, "method not allowed")
        return {"status": 200, "body": {"commands": [
            {"name": name, "aliases": list(aliases), "usage": usage, "summary": summary}
            for name, usage, summary, aliases in helpdata.COMMANDS
        ]}}
    if not path.startswith(PREFIX) or len(path) == len(PREFIX):
        return _error(404, f"no route: {method} {path}")
    if method != "POST":
        return _error(405, "method not allowed")
    name = path[len(PREFIX):]
    body = request.get("body")
    if body is None:
        body = {}
    args = body.get("args", []) if isinstance(body, dict) else None
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return _error(400, "body.args must be a list of strings")
    try:
        out = _dispatch(store, name, args)
    except TaskmanError as e:
        return _error(STATUS.get(e.kind, 500), e.message, e.kind)
    if out is None:
        return _error(404, f"unknown command: {name}")
    return {"status": 200, "body": {"output": out, "lines": out.splitlines()}}
