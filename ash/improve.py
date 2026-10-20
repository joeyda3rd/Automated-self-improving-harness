"""Slow loop: the harness proposes a change to itself, the benchmark decides whether it stays.

  evidence -> improver session in a worktree of the harness -> kernel diff check
  -> benchmark candidate vs baseline -> merge (accepted) or discard (rejected) -> log
"""
import os
import time
from collections import Counter

from . import evals, gitops
from .claude import IMPROVE_SCHEMA, run_session
from .config import append_jsonl, load_json, read_jsonl, save_json
from .memory import read_lessons


def log(msg):
    print(f"[ash improve {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def evidence(harness, window=30):
    """A compact brief of how the harness has been doing, for the improver to read."""
    builds = [r for r in read_jsonl(harness.metrics) if r.get("kind") == "build"][-window:]
    outcomes = Counter(r["outcome"] for r in builds)
    n = len(builds) or 1
    lines = [
        "# ASH improvement evidence", "",
        f"## Last {len(builds)} build runs",
        f"- outcomes: {dict(outcomes)}",
        f"- mean cost ${sum(r.get('cost_usd', 0) for r in builds) / n:.3f}, "
        f"mean turns {sum(r.get('turns', 0) for r in builds) / n:.1f}",
        f"- stop-gate bounces {sum(r.get('gate_failures', 0) for r in builds)}, "
        f"guard denials {sum(r.get('guard_denials', 0) for r in builds)}, "
        f"tool errors {sum(r.get('tool_errors', 0) for r in builds)}",
        "", "## Unsuccessful runs",
    ]
    lines += [f"- {r['task']} {r['title']!r}: {r['outcome']}: {r.get('note', '')[:240]} (run dir {r['run_dir']})"
              for r in builds if r["outcome"] != "done"][-12:] or ["- none"]
    lines += ["", "## Retro suggestions about the harness"]
    lines += [f"- ({s['task']}, {s['outcome']}) {s['suggestion'][:400]}"
              for s in read_jsonl(os.path.join(harness.state, "suggestions.jsonl"))[-12:]] or ["- none"]
    lines += ["", "## Current lessons (state/learnings.md)"] + (read_lessons(harness.learnings)[-30:] or ["- none"])
    lines += ["", "## Earlier improvement attempts (do not repeat rejected ideas without new evidence)"]
    lines += [f"- {'ACCEPTED' if i.get('accepted') else 'REJECTED'}: {i.get('hypothesis', '')[:200]} -> {i.get('reason')}"
              for i in read_jsonl(harness.improvements)[-15:]] or ["- none"]
    return "\n".join(lines) + "\n"


def baseline(harness, commit):
    cache_path = os.path.join(harness.state, "eval_cache.json")
    cache = load_json(cache_path, {}) or {}
    if commit not in cache:
        log(f"benchmarking baseline {commit[:12]}")
        cache[commit] = evals.run_suite(harness, harness.plugin_dir, f"baseline-{commit[:12]}")
        save_json(cache_path, cache)
    return cache[commit]


def cycle(harness):
    """Run one improvement attempt. Returns the logged decision record (or None if skipped)."""
    if not evals.discover(harness):
        log("no evals in evals/tasks; skipping (self-improvement needs a benchmark)")
        return None
    if not gitops.is_repo(harness.home):
        log("harness is not a git repository; skipping")
        return None
    mutable = harness.get("mutable_paths", [])
    base_commit = gitops.head(harness.home)
    base = baseline(harness, base_commit)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(harness.runs_dir, f"{stamp}-improve")
    os.makedirs(run_dir, exist_ok=True)
    evidence_path = os.path.join(run_dir, "evidence.md")
    with open(evidence_path, "w", encoding="utf-8") as fh:
        fh.write(evidence(harness))
        fh.write(f"\n## Benchmark of the current harness\n- pass rate {base['pass_rate']:.0%}, "
                 f"mean cost ${base['cost_usd']:.3f}, mean turns {base['turns']}\n")

    branch = f"ash-improve/{stamp}"
    wt = os.path.join(harness.state, "worktrees", f"improve-{stamp}")
    gitops.add_worktree(harness.home, wt, branch, base_commit)
    record = {"ts": time.time(), "base_commit": base_commit[:12], "run_dir": run_dir, "accepted": False}
    try:
        res = run_session(harness, role="improver", cwd=wt, run_dir=run_dir, schema=IMPROVE_SCHEMA,
                          prompt=("Use the ash:improve-harness skill. The current directory is a worktree of the "
                                  f"harness. Evidence: {evidence_path}"),
                          budget_usd=harness.get("improve_budget_usd", 5.0),
                          extra_env={"ASH_WRITE_ROOTS": ":".join(mutable)})
        record.update({k: res.output.get(k, "") for k in ("hypothesis", "change_summary", "expected_effect")})
        record["cost_usd"] = res.cost_usd
        changed = gitops.changed_files(wt, base_commit)
        record["changed"] = changed
        illegal = [f for f in changed if not any(f.startswith(m) for m in mutable)]
        if not changed:
            record["reason"] = "no change proposed"
        elif illegal:
            record["reason"] = f"touched immutable paths: {illegal}"
        else:
            cand = evals.run_suite(harness, os.path.join(wt, "plugin"), f"candidate-{stamp}")
            accepted, reason = evals.better(base, cand, harness.get("improve_min_cost_gain", 0.05))
            record.update({"accepted": accepted, "reason": reason,
                           "baseline": {k: base[k] for k in ("pass_rate", "cost_usd", "turns")},
                           "candidate": {k: cand[k] for k in ("pass_rate", "cost_usd", "turns")}})
            if accepted:
                gitops.commit_all(wt, f"ASH self-improvement: {record['change_summary'][:60]}\n\n"
                                      f"Hypothesis: {record['hypothesis']}\nEvidence: {reason}")
                if gitops.merge(harness.home, branch, f"Merge {branch}: {reason}"):
                    cache_path = os.path.join(harness.state, "eval_cache.json")
                    cache = load_json(cache_path, {}) or {}
                    cache[gitops.head(harness.home)] = cand
                    save_json(cache_path, cache)
                else:
                    record.update({"accepted": False, "reason": reason + "; but merging into the harness failed"})
    finally:
        gitops.remove_worktree(harness.home, wt, branch)
    append_jsonl(harness.improvements, record)
    log(f"{'ACCEPTED' if record['accepted'] else 'rejected'}: {record.get('hypothesis', '')[:80]} ({record['reason']})")
    return record
