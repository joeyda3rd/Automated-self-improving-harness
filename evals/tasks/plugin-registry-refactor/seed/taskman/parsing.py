"""Parsing of command arguments shared by every entry point."""
import datetime
import re

from .errors import UsageError, ValidationError
from .models import PRIORITIES

_PRIORITY_ABBREV = {p[0]: p for p in PRIORITIES}
_TAG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_REL = re.compile(r"^\+(\d{1,3})d$")


def parse_id(text):
    s = text[1:] if text.startswith("#") else text
    if not s.isdigit() or int(s) == 0:
        raise UsageError(f"invalid task id: {text}")
    return int(s)


def parse_priority(text):
    s = text.strip().lower()
    s = _PRIORITY_ABBREV.get(s, s)
    if s not in PRIORITIES:
        raise ValidationError(f"invalid priority: {text} (expected one of {', '.join(PRIORITIES)})")
    return s


def parse_date(text, today):
    s = text.strip().lower()
    if s == "today":
        return today.isoformat()
    if s == "tomorrow":
        return (today + datetime.timedelta(days=1)).isoformat()
    m = _REL.match(s)
    if m:
        return (today + datetime.timedelta(days=int(m.group(1)))).isoformat()
    try:
        return datetime.date.fromisoformat(s).isoformat() if len(s) == 10 else _bad_date(text)
    except ValueError:
        _bad_date(text)


def _bad_date(text):
    raise ValidationError(f"invalid date: {text}")


def parse_tags(text):
    tags = []
    for raw in text.split(","):
        t = raw.strip().lower().lstrip("#")
        if not t:
            continue
        if not _TAG.match(t):
            raise ValidationError(f"invalid tag: {raw.strip()}")
        if t not in tags:
            tags.append(t)
    if not tags:
        raise ValidationError("no tags given")
    return tags


def split_options(args, options, flags=()):
    """Split args into (positional, opts). `options` take a value, `flags` don't.

    Option names map to their canonical key, e.g. {"-p": "priority", "--priority": "priority"}.
    """
    positional, opts = [], {}
    i = 0
    while i < len(args):
        a = args[i]
        if a in flags:
            opts[flags[a]] = True
        elif a in options:
            if i + 1 >= len(args):
                raise UsageError(f"option {a} needs a value")
            opts[options[a]] = args[i + 1]
            i += 1
        elif a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
            raise UsageError(f"unknown option: {a}")
        else:
            positional.append(a)
        i += 1
    return positional, opts
