#!/usr/bin/env python3
"""ASH kernel hooks: one dispatcher for every Claude Code hook event the harness uses.

Usage (from hooks.json): ash_hook.py <session-start|guard|telemetry|stop-gate|pre-compact|session-end>

The hook reads the event JSON on stdin and the run context from the environment
the orchestrator sets for each headless session:

  ASH_HOME          harness root (memory lives in $ASH_HOME/state)
  ASH_RUN_DIR       directory of the current run record (unset => interactive use)
  ASH_ROLE          builder | planner | retro | improver | eval
  ASH_VERIFY_CMD    command whose exit status decides whether the work is done
  ASH_GATE_MAX      how many times the stop gate may send the agent back (default 3)
  ASH_WRITE_ROOTS   ':'-separated paths (relative to cwd) the session may write;
                    unset means "anywhere under cwd"
  ASH_LESSONS       ':'-separated lesson files injected at session start

This file is part of the kernel: improvement runs are not allowed to edit it, so
the agent can never loosen its own guardrails or its own definition of "done".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

KERNEL_PARTS = ("ash/", "plugin/hooks/", "evals/", "harness.json", "bin/", "tests/")

DANGEROUS_BASH = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)(\s|$)", "recursive delete of / or home"),
    (r"\bgit\s+push\b", "pushing is the orchestrator's job, not the session's"),
    (r"\bgit\s+(checkout|switch)\s+(main|master)\b", "stay on the task branch"),
    (r"\bgit\s+config\s+--global\b", "global git config"),
    (r"\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b", "piping a download into a shell"),
    (r"\bsudo\b", "sudo"),
    (r"\b(mkfs|shutdown|reboot)\b|\bdd\s+if=", "system-level destructive command"),
    (r"(^|\s)(ASH_[A-Z_]+)=", "rewriting the harness environment"),
]


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def env(name, default=None):
    value = os.environ.get(name)
    return value if value else default


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def tail_lines(path, n):
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [l.rstrip("\n") for l in fh if l.strip()]
    except OSError:
        return []
    return lines[-n:]


def read_text(path, limit=6000):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()[:limit]
    except OSError:
        return ""


# ---------------------------------------------------------------- session-start

def session_start(event):
    home = env("ASH_HOME")
    role = env("ASH_ROLE", "interactive")
    cwd = event.get("cwd") or os.getcwd()
    parts = [f"[ASH] You are running inside the Automated Self-improving Harness as role `{role}`."]
    files = env("ASH_LESSONS", os.path.join(home, "state", "learnings.md") if home else "")
    lessons = [l for f in files.split(":") if f for l in tail_lines(f, 30)]
    if lessons:
        parts.append("Lessons the harness learned from earlier runs (newest last). Apply them:\n" + "\n".join(lessons))
    notes = read_text(os.path.join(cwd, ".ash", "notes.md"), 4000)
    if notes:
        parts.append("Project notes kept by earlier sessions (.ash/notes.md):\n" + notes)
    verify = env("ASH_VERIFY_CMD")
    if verify and role in ("builder", "eval"):
        parts.append(f"Your work is only accepted when `{verify}` exits 0. A stop hook runs it when you finish.")
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}})


# ------------------------------------------------------------------------ guard

def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def _deny(reason):
    run_dir = env("ASH_RUN_DIR")
    if run_dir:
        append_jsonl(os.path.join(run_dir, "guard.jsonl"), {"ts": time.time(), "denied": reason})
    emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                 "permissionDecisionReason": f"ASH guard: {reason}"}})


def check_write(path, cwd):
    """Return a denial reason for writing `path`, or None when allowed."""
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    home = env("ASH_HOME")
    role = env("ASH_ROLE", "interactive")
    if role == "interactive":
        return None
    allowed_roots = [cwd, "/tmp"]
    if env("ASH_RUN_DIR"):
        allowed_roots.append(env("ASH_RUN_DIR"))
    if not any(_inside(path, r) for r in allowed_roots):
        return f"{path} is outside the workspace"
    if home and _inside(path, home) and not _inside(cwd, home):
        return "sessions working on a project may not modify the harness"
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd))
    if role == "improver" and any(rel == k.rstrip("/") or rel.startswith(k) for k in KERNEL_PARTS):
        return f"{rel} belongs to the kernel (evaluator, guardrails, orchestrator) and is immutable to self-improvement"
    if rel.startswith(".ash/") and rel != ".ash/notes.md":
        return "harness state in .ash/ is owned by the orchestrator (only .ash/notes.md is yours)"
    roots = env("ASH_WRITE_ROOTS")
    if roots and _inside(path, cwd):
        if not any(_inside(path, os.path.join(cwd, r)) for r in roots.split(":") if r):
            return f"{rel} is outside the writable roots for role {role}: {roots}"
    return None


def _hidden_roots(cwd):
    """Benchmark material builders and improvers must not see (no teaching to the test)."""
    if env("ASH_ROLE", "interactive") not in ("builder", "eval", "improver"):
        return []
    roots = [os.path.join(env("ASH_HOME"), "evals")] if env("ASH_HOME") else []
    if env("ASH_ROLE") == "improver":
        roots.append(os.path.join(cwd, "evals"))
    return roots


def guard(event):
    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    hidden = _hidden_roots(cwd)
    if tool in ("Read", "Grep", "Glob"):
        path = tin.get("file_path") or tin.get("path") or cwd
        path = path if os.path.isabs(path) else os.path.join(cwd, path)
        if any(_inside(path, h) for h in hidden):
            return _deny("evaluation material is hidden from build and improvement sessions")
        return None
    if tool == "Bash":
        command = tin.get("command", "")
        if hidden and re.search(r"(^|[\s/\"'])evals(/|\s|$)", command):
            return _deny("evaluation material is hidden from build and improvement sessions")
        if env("ASH_ROLE", "interactive") != "interactive":
            for pattern, why in DANGEROUS_BASH:
                if re.search(pattern, command):
                    return _deny(f"blocked command ({why})")
            if env("ASH_ROLE") == "improver" and re.search(r"(>|\btee\b|\bmv\b|\bcp\b|\bsed\s+-i).*\b(ash/|plugin/hooks/|evals/|harness\.json)", command):
                return _deny("shell writes to the kernel are not allowed for improvement runs")
        return None
    path = tin.get("file_path") or tin.get("notebook_path")
    if path:
        reason = check_write(path, cwd)
        if reason:
            return _deny(reason)
    return None


# -------------------------------------------------------------------- telemetry

def telemetry(event):
    run_dir = env("ASH_RUN_DIR")
    if not run_dir:
        return
    resp = event.get("tool_response")
    is_error = False
    if isinstance(resp, dict):
        is_error = bool(resp.get("is_error") or resp.get("error") or resp.get("interrupted"))
        code = resp.get("exit_code", resp.get("returnCode"))
        if isinstance(code, int) and code != 0:
            is_error = True
    tin = event.get("tool_input") or {}
    summary = tin.get("command") or tin.get("file_path") or tin.get("pattern") or tin.get("description") or ""
    append_jsonl(os.path.join(run_dir, "tools.jsonl"), {
        "ts": time.time(),
        "event": event.get("hook_event_name"),
        "tool": event.get("tool_name") or event.get("agent_type") or "",
        "error": is_error,
        "input": str(summary)[:200],
    })


# -------------------------------------------------------------------- stop-gate

def stop_gate(event):
    run_dir = env("ASH_RUN_DIR")
    verify = env("ASH_VERIFY_CMD")
    if not run_dir or not verify or env("ASH_ROLE") not in ("builder", "eval"):
        return
    gate_log = os.path.join(run_dir, "gate.jsonl")
    failures = sum(1 for l in tail_lines(gate_log, 1000) if '"passed": false' in l)
    max_attempts = int(env("ASH_GATE_MAX", "3"))
    cwd = event.get("cwd") or os.getcwd()
    started = time.time()
    try:
        proc = subprocess.run(verify, shell=True, cwd=cwd, capture_output=True, text=True,
                              timeout=int(env("ASH_VERIFY_TIMEOUT", "600")))
        passed, output = proc.returncode == 0, (proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired:
        passed, output = False, "verification timed out"
    append_jsonl(gate_log, {"ts": started, "passed": passed, "seconds": round(time.time() - started, 1)})
    if passed or failures + 1 >= max_attempts:
        return  # let the session end; the orchestrator re-verifies independently
    emit({"decision": "block", "reason": (
        f"ASH stop gate: `{verify}` failed (attempt {failures + 1}/{max_attempts}). "
        "Do not stop yet. Diagnose the failure below, fix the code (never the tests' intent), "
        "and finish again.\n\n" + output[-4000:])})


# ------------------------------------------------------- pre-compact / session-end

def pre_compact(event):
    run_dir = env("ASH_RUN_DIR")
    if run_dir:
        append_jsonl(os.path.join(run_dir, "events.jsonl"), {"ts": time.time(), "event": "compact",
                                                             "trigger": event.get("trigger")})


def session_end(event):
    run_dir = env("ASH_RUN_DIR")
    src = event.get("transcript_path")
    if run_dir and src and os.path.exists(src):
        os.makedirs(run_dir, exist_ok=True)
        name = f"transcript-{event.get('session_id', 'session')}.jsonl"
        shutil.copyfile(src, os.path.join(run_dir, name))


HANDLERS = {
    "session-start": session_start,
    "guard": guard,
    "telemetry": telemetry,
    "stop-gate": stop_gate,
    "pre-compact": pre_compact,
    "session-end": session_end,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in HANDLERS:
        sys.stderr.write("usage: ash_hook.py " + "|".join(HANDLERS) + "\n")
        return 1
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    HANDLERS[sys.argv[1]](event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
