"""Batch runner: execute a script of commands, one per line, against one store.

Lines are split like a shell would (shlex). Blank lines and lines starting with '#' are skipped.
The transcript has "> LINE" for each command, followed by its output lines, or "! KIND: MESSAGE"
on failure. Execution stops at the first failure unless continue_on_error is true. The last line
is "= N ok, M failed".
"""
import shlex

from .errors import TaskmanError
from .registry import UnknownCommandError, registry


def run_batch(store, lines, continue_on_error=False):
    transcript = []
    ok = failed = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        transcript.append(f"> {line}")
        try:
            words = shlex.split(line)
        except ValueError as e:
            transcript.append(f"! parse: {e}")
            failed += 1
            if continue_on_error:
                continue
            break
        try:
            out = registry.resolve(words[0]).func(store, words[1:])
        except UnknownCommandError:
            transcript.append(f"! unknown: unknown command: {words[0]}")
        except TaskmanError as e:
            transcript.append(f"! {e.kind}: {e.message}")
        else:
            ok += 1
            if out:
                transcript.extend(out.splitlines())
            continue
        failed += 1
        if not continue_on_error:
            break
    transcript.append(f"= {ok} ok, {failed} failed")
    return transcript


def run_file(store, path, continue_on_error=False):
    with open(path, encoding="utf-8") as f:
        return run_batch(store, f.read().splitlines(), continue_on_error)
