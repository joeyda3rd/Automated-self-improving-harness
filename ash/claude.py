"""Run one headless Claude Code session (`claude -p`) with the ASH plugin loaded."""
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

from .config import append_jsonl, read_jsonl, save_json

BUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["done", "blocked", "failed"]},
        "summary": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "follow_ups": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "spec": {"type": "string"}},
            "required": ["title", "spec"]}},
    },
    "required": ["status", "summary"],
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "spec": {"type": "string"},
                "acceptance": {"type": "array", "items": {"type": "string"}},
                "depends_on": {"type": "array", "items": {"type": "integer"}},
                "priority": {"type": "integer"},
            },
            "required": ["title", "spec"]}},
        "verify_cmd": {"type": "string"},
    },
    "required": ["tasks"],
}

RETRO_SCHEMA = {
    "type": "object",
    "properties": {
        "lessons": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"},
                           "scope": {"type": "string", "enum": ["project", "harness"]}},
            "required": ["text", "scope"]}},
        "lesson_feedback": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"},
                           "verdict": {"type": "string", "enum": ["helpful", "harmful", "irrelevant"]}},
            "required": ["id", "verdict"]}},
        "harness_suggestion": {"type": "string"},
    },
    "required": ["lessons"],
}

IMPROVE_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {"type": "string"},
        "change_summary": {"type": "string"},
        "expected_effect": {"type": "string"},
    },
    "required": ["hypothesis", "change_summary"],
}


INHERITED_SESSION_VARS = {"CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID",
                          "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_AFTER_LAST_COMPACT", "CLAUDECODE",
                          "CLAUDE_EFFORT"}  # effort is set explicitly per role, never inherited


class BudgetExceeded(RuntimeError):
    """The harness-wide spend limit (`budget_usd_total`) is reached; no new session may start."""


def ledger_path(harness):
    return os.path.join(harness.state, "spend.jsonl")


def spent(harness):
    """Dollars spent by every session the harness has launched (builds, plans, retros, evals, improvements)."""
    path = ledger_path(harness)
    if not os.path.exists(path):  # first use: backfill from the per-run session logs
        import glob
        for f in sorted(glob.glob(os.path.join(harness.state, "**", "sessions.jsonl"), recursive=True)):
            for r in read_jsonl(f):
                append_jsonl(path, {"ts": r.get("ts"), "role": r.get("role"), "cost_usd": r.get("cost_usd", 0),
                                    "backfilled": True})
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "a").close()
    return round(sum(r.get("cost_usd", 0) for r in read_jsonl(path)), 4)


_reserved = 0.0  # dollars promised to sessions still running in this process (parallel evals)
_reserve_lock = threading.Lock()


def remaining(harness):
    limit = harness.get("budget_usd_total")
    return None if not limit else max(0.0, limit - spent(harness) - _reserved)


@dataclass
class SessionResult:
    ok: bool
    output: dict = field(default_factory=dict)
    session_id: str = ""
    cost_usd: float = 0.0
    turns: int = 0
    seconds: float = 0.0
    error: str = ""


def _parse_output(stdout):
    """Pull the result envelope and the structured output out of `--output-format json`."""
    envelope = {}
    for candidate in (stdout.strip(), stdout.strip().splitlines()[-1] if stdout.strip() else ""):
        try:
            envelope = json.loads(candidate)
            break
        except ValueError:
            continue
    if isinstance(envelope, list):  # stream of messages: keep the result message
        envelope = next((m for m in reversed(envelope) if m.get("type") == "result"), {})
    structured = envelope.get("structured_output")
    if not isinstance(structured, dict):
        text = envelope.get("result") or ""
        match = re.search(r"\{.*\}", text, re.S)
        try:
            structured = json.loads(match.group(0)) if match else {}
        except ValueError:
            structured = {}
    return envelope, structured


def role_prompt(plugin_dir, role):
    path = os.path.join(plugin_dir, "roles", f"{role}.md")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def run_session(harness, *, prompt, role, cwd, run_dir, schema=None, plugin_dir=None,
                resume=None, budget_usd=None, extra_env=None, timeout=3600):
    """Run one `claude -p` session and return its parsed result.

    The session gets the ASH plugin (skills, subagents, kernel hooks), the role's
    system prompt, a budget cap, and the run context in its environment so the
    hooks can find the run record.
    """
    global _reserved
    with _reserve_lock:  # concurrent sessions each reserve their cap, so together they cannot overspend
        left = remaining(harness)
        if left is not None:
            if left <= 0.01:
                raise BudgetExceeded(f"total budget ${harness.get('budget_usd_total')} is spent")
            budget_usd = min(budget_usd or left, left)
        reserved = budget_usd if left is not None else 0.0
        _reserved += reserved
    try:
        return _run_session(harness, prompt=prompt, role=role, cwd=cwd, run_dir=run_dir, schema=schema,
                            plugin_dir=plugin_dir, resume=resume, budget_usd=budget_usd,
                            extra_env=extra_env, timeout=timeout)
    finally:
        with _reserve_lock:
            _reserved -= reserved


def _run_session(harness, *, prompt, role, cwd, run_dir, schema, plugin_dir, resume, budget_usd,
                 extra_env, timeout):
    plugin_dir = plugin_dir or harness.plugin_dir
    session_id = resume or str(uuid.uuid4())
    cmd = [harness.claude_bin, "-p", prompt, "--output-format", "json",
           "--plugin-dir", plugin_dir,
           "--permission-mode", harness.get("permission_mode", "bypassPermissions")]
    cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
    if not resume:
        cmd += ["--append-system-prompt", role_prompt(plugin_dir, role)]
    if harness.get("model"):
        cmd += ["--model", harness.get("model")]
    effort = (harness.get("effort") or {}).get(role) or (harness.get("effort") or {}).get("default")
    if effort:
        cmd += ["--effort", effort]
    if budget_usd:
        cmd += ["--max-budget-usd", str(budget_usd)]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    if (extra_env or {}).get("ASH_ROLE", role) == "eval":
        cmd += ["--disallowedTools", "WebFetch", "WebSearch"]  # benchmark runs must not look up answers

    # A harness launched from inside another Claude Code session must not leak that
    # session's identity into its children, or --session-id/--resume address the parent.
    env = {k: v for k, v in os.environ.items() if k not in INHERITED_SESSION_VARS}
    env.update({
        "ASH_HOME": harness.home,
        "ASH_ROLE": role,
        "ASH_RUN_DIR": run_dir,
        "ASH_PLUGIN_DIR": plugin_dir,  # skills call helper tools as "$ASH_PLUGIN_DIR/bin/<tool>"
        "ASH_GATE_MAX": str(harness.get("gate_max", 3)),
        "ASH_VERIFY_TIMEOUT": str(harness.get("verify_timeout_seconds", 900)),
    })
    env.update({k: v for k, v in (extra_env or {}).items() if v is not None})

    os.makedirs(run_dir, exist_ok=True)
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or "", f"session timed out after {timeout}s", -1
    except FileNotFoundError:
        stdout, stderr, code = "", f"claude binary not found: {harness.claude_bin}", -1
    seconds = round(time.time() - started, 1)

    envelope, structured = _parse_output(stdout if isinstance(stdout, str) else stdout.decode())
    result = SessionResult(
        ok=code == 0 and not envelope.get("is_error", False),
        output=structured,
        session_id=envelope.get("session_id") or session_id,
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        turns=int(envelope.get("num_turns") or 0),
        seconds=seconds,
        error="" if code == 0 else (stderr or "")[-2000:],
    )
    spent(harness)  # make sure the ledger exists (and is backfilled) before adding to it
    append_jsonl(ledger_path(harness), {"ts": started, "role": role, "cost_usd": result.cost_usd,
                                        "run_dir": run_dir})
    append_jsonl(os.path.join(run_dir, "sessions.jsonl"), {
        "ts": started, "role": role, "session_id": result.session_id, "resumed": bool(resume),
        "ok": result.ok, "cost_usd": result.cost_usd, "turns": result.turns,
        "seconds": seconds, "error": result.error[:500],
    })
    save_json(os.path.join(run_dir, f"{role}-output.json"), structured)
    return result
