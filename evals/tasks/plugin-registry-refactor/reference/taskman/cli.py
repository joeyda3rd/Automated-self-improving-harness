"""Command-line entry point: python3 -m taskman [--db PATH] COMMAND [ARGS...]

Exit codes: 0 ok, 1 task error (not found, conflict, invalid value), 2 usage error or unknown command.
"""
import os
import sys

from .commands import help_text
from .errors import TaskmanError, UsageError
from .registry import UnknownCommandError, registry
from .store import Store

DEFAULT_DB = "tasks.json"


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
        print(help_text(), file=stdout)
        return 0
    name, args = argv[0], argv[1:]
    try:
        cmd = registry.resolve(name)
    except UnknownCommandError:
        print(f"error: unknown command: {name} (try 'help')", file=stderr)
        return 2
    try:
        out = cmd.func(Store(db), args)
    except UsageError as e:
        print(f"error: {e.message}", file=stderr)
        return 2
    except TaskmanError as e:
        print(f"error: {e.message}", file=stderr)
        return 1
    if out:
        print(out, file=stdout)
    return 0
