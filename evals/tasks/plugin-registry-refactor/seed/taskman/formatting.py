"""Text rendering of tasks and summaries."""
import csv
import io
import json

from .models import PRIORITIES

_MARK = {"urgent": "!! ", "high": "! ", "normal": "", "low": "~ "}


def due_note(task, today):
    if not task.due:
        return ""
    note = f"due {task.due}"
    if not task.done:
        iso = today.isoformat()
        if task.due < iso:
            note += " (overdue)"
        elif task.due == iso:
            note += " (today)"
    return note


def task_line(task, today):
    line = f"#{task.id:<3} [{'x' if task.done else ' '}] {_MARK[task.priority]}{task.title}"
    if task.tags:
        line += "  " + " ".join("#" + t for t in task.tags)
    note = due_note(task, today)
    if note:
        line += "  " + note
    return line


def task_lines(tasks, today, empty="no tasks"):
    if not tasks:
        return empty
    return "\n".join(task_line(t, today) for t in tasks)


def task_detail(task, today):
    note = due_note(task, today)
    return "\n".join([
        f"#{task.id} {task.title}",
        f"status: {'done' if task.done else 'open'}",
        f"priority: {task.priority}",
        f"tags: {', '.join(task.tags) if task.tags else '(none)'}",
        f"due: {note[4:] if note else '(none)'}",
        f"created: {task.created or '(unknown)'}",
    ])


def tags_line(task):
    return f"#{task.id} tags: {', '.join(task.tags) if task.tags else '(none)'}"


def stats_text(stats):
    by_pri = " ".join(f"{p}={stats['by_priority'][p]}" for p in reversed(PRIORITIES))
    return "\n".join([
        f"total: {stats['total']}",
        f"open: {stats['open']}",
        f"done: {stats['done']}",
        f"overdue: {stats['overdue']}",
        f"by priority: {by_pri}",
    ])


def export_csv(tasks):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "title", "done", "priority", "tags", "due"])
    for t in tasks:
        w.writerow([t.id, t.title, "yes" if t.done else "no", t.priority, " ".join(t.tags), t.due or ""])
    return buf.getvalue().rstrip("\n")


def export_json(tasks):
    return json.dumps([t.to_dict() for t in tasks], sort_keys=True)


def help_text(entries):
    lines = ["commands:"]
    for usage, summary, aliases in entries:
        line = f"  {usage:<36}{summary}"
        if aliases:
            line += f" (aliases: {', '.join(aliases)})"
        lines.append(line)
    return "\n".join(lines)
