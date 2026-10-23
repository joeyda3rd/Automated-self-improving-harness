"""Test-integrity check run on every task diff before it is merged.

Removing or skipping tests is the cheapest way to turn a red build green, and
practitioners running autonomous loops report it as a top failure mode. The
orchestrator therefore refuses diffs that delete test files, remove more test
cases than they add, or add skip markers, unless the task card asks for it.
"""
import re

from . import gitops

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.[^/]+$|\.(test|spec)\.[^/]+$")
TEST_CASE = re.compile(r"^\s*(def test_\w+|async def test_\w+|func Test\w+|(it|test)\s*\(|#\[test\])")
SKIP = re.compile(r"@(unittest\.)?skip|pytest\.mark\.(skip|xfail)|\b(it|test|describe)\.(skip|todo)\(|\bx(it|describe)\(|"
                  r"\bt\.Skip\(|#\[ignore\]|\bself\.skipTest\(")
ALLOWED = re.compile(r"\b(skip|remov|delet|disabl|drop)\w*\b[^.]*\btests?\b|\btests?\b[^.]*\b(skip|remov|delet|disabl|drop)\w*",
                     re.I)


def allowed_by(task):
    text = " ".join([task.get("title", ""), task.get("spec", "")] + task.get("acceptance", []))
    return bool(ALLOWED.search(text))


def check(repo, base):
    """Problems with the test changes between `base` and HEAD in `repo` (empty list: fine)."""
    problems = []
    status = gitops.git(repo, "diff", "--name-status", f"{base}...HEAD")
    for line in status.splitlines():
        parts = line.split("\t")
        if parts[0].startswith("D") and TEST_PATH.search(parts[-1]):
            problems.append(f"deleted test file {parts[-1]}")
    diff = gitops.git(repo, "diff", "-U0", f"{base}...HEAD")
    current, added, removed = None, 0, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            continue
        if line.startswith("--- ") or current is None or not TEST_PATH.search(current):
            continue
        if line.startswith("+"):
            added += bool(TEST_CASE.match(line[1:]))
            if SKIP.search(line):
                problems.append(f"added a skip marker in {current}: {line[1:].strip()[:80]}")
        elif line.startswith("-"):
            removed += bool(TEST_CASE.match(line[1:]))
    if removed > added:
        problems.append(f"removed {removed} test cases and added {added}")
    return problems
