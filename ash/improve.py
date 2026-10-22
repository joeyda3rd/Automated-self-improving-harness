"""Slow loop: the harness proposes a change to itself, the benchmark decides whether it stays.

  evidence -> improver session in a worktree of the harness -> kernel diff check
  -> benchmark candidate vs baseline -> merge (accepted) or discard (rejected) -> log
"""
import os
import time
from collections import Counter

from . import evals, gitops
from .claude import IMPROVE_SCHEMA, BudgetExceeded, run_session
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


def gate_repeats(harness):
    return int(harness.get("improve_eval_repeats") or harness.get("eval_repeats", 1))


def plugin_tree(harness, commit):
    """Git tree hash of plugin/ at `commit`: the genome being scored. Baselines are keyed by it,
    so kernel or doc commits that leave the plugin unchanged reuse the benchmark."""
    return gitops.git(harness.home, "rev-parse", f"{commit}:plugin")


def cache_key(harness, commit):
    """A baseline is only reusable for the same harness, eval set and repeat count."""
    import hashlib
    names = ",".join(sorted(evals.gate_set(harness)))
    key = f"{commit}|{hashlib.sha1(names.encode()).hexdigest()[:8]}|r{gate_repeats(harness)}"
    effort = harness.get("effort") or {}
    builder_effort = effort.get("builder") or effort.get("default")
    return key + (f"|e{builder_effort}" if builder_effort and builder_effort != "medium" else "")


def benchmark_failures(summary, limit=8):
    """Failed eval runs, as the builder saw them: its own report and transcript, never the hidden check."""
    failed = [r for r in summary.get("results", []) if not r.get("passed")][:limit]
    if not failed:
        return "- every gate eval passed; look for cost and turn savings\n"
    lines = ["\n## Benchmark tasks the current harness failed",
             "(hidden checks stay hidden: work out from the transcript what the builder missed and what "
             "general habit would have caught it; do not target these specific tasks)"]
    for r in failed:
        out = load_json(os.path.join(r.get("run_dir", ""), "builder-output.json"), {}) or {}
        lines.append(f"- {r['eval']} ({r.get('title', '')}): builder reported {out.get('status', '?')!r}: "
                     f"{str(out.get('summary', ''))[:500]} [transcript in {r.get('run_dir', '?')}]")
    return "\n".join(lines) + "\n"


def baseline(harness, commit):
    cache_path = os.path.join(harness.state, "eval_cache.json")
    cache = load_json(cache_path, {}) or {}
    key = cache_key(harness, commit)
    if "per_task" not in cache.get(key, {}):
        log(f"benchmarking baseline (plugin {commit[:12]}) on {len(evals.gate_set(harness))} evals")
        summary = evals.run_suite(harness, harness.plugin_dir, f"baseline-{commit[:12]}",
                                  names=evals.gate_set(harness), repeats=gate_repeats(harness), resumable=True)
        if summary.get("incomplete"):
            raise BudgetExceeded("total budget reached while benchmarking the baseline")
        cache[key] = summary
        save_json(cache_path, cache)
    return cache[key]


def cycle(harness):
    """Run one improvement attempt. Returns the logged decision record (or None if skipped)."""
    if not evals.gate_set(harness):
        log("no evals in evals/tasks; skipping (self-improvement needs a benchmark)")
        return None
    if not gitops.is_repo(harness.home):
        log("harness is not a git repository; skipping")
        return None
    import glob
    for stale in glob.glob(os.path.join(harness.state, "worktrees", "improve-*")):  # left by an interrupted cycle
        gitops.remove_worktree(harness.home, stale, "ash-improve/" + os.path.basename(stale)[len("improve-"):])
    mutable = harness.get("mutable_paths", [])
    base_commit = gitops.head(harness.home)
    base = baseline(harness, plugin_tree(harness, base_commit))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(harness.runs_dir, f"{stamp}-improve")
    os.makedirs(run_dir, exist_ok=True)
    evidence_path = os.path.join(run_dir, "evidence.md")
    with open(evidence_path, "w", encoding="utf-8") as fh:
        fh.write(evidence(harness))
        fh.write(f"\n## Benchmark of the current harness\n- pass rate {base['pass_rate']:.0%}, "
                 f"mean cost ${base['cost_usd']:.3f}, mean turns {base['turns']}\n")
        fh.write(benchmark_failures(base))

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
            candidate_plugin = os.path.join(wt, "plugin")
            smoke = evals.smoke_set(harness)
            early = evals.run_suite(harness, candidate_plugin, f"candidate-{stamp}-smoke", names=smoke,
                                    repeats=gate_repeats(harness)) \
                if smoke else None
            if early and evals.regressions(base, early):
                cand, accepted = early, False
                reason = f"failed the smoke stage: regressed on {evals.regressions(base, early)}"
            else:
                rest = evals.run_suite(harness, candidate_plugin, f"candidate-{stamp}",
                                       names=evals.gate_set(harness) - smoke, repeats=gate_repeats(harness))
                cand = evals.summarize(f"candidate-{stamp}", (early["results"] if early else []) + rest["results"])
                accepted, reason = evals.better(base, cand, harness.get("improve_min_cost_gain", 0.05))
            record.update({"accepted": accepted, "reason": reason,
                           "baseline": {k: base[k] for k in ("pass_rate", "cost_usd", "turns", "per_task")},
                           "candidate": {k: cand[k] for k in ("pass_rate", "cost_usd", "turns", "per_task")}})
            if accepted:
                gitops.commit_all(wt, f"ASH self-improvement: {record['change_summary'][:60]}\n\n"
                                      f"Hypothesis: {record['hypothesis']}\nEvidence: {reason}")
                if gitops.merge(harness.home, branch, f"Merge {branch}: {reason}"):
                    cache_path = os.path.join(harness.state, "eval_cache.json")
                    cache = load_json(cache_path, {}) or {}
                    cache[cache_key(harness, plugin_tree(harness, gitops.head(harness.home)))] = cand
                    save_json(cache_path, cache)
                else:
                    record.update({"accepted": False, "reason": reason + "; but merging into the harness failed"})
    finally:
        gitops.remove_worktree(harness.home, wt, branch)
    append_jsonl(harness.improvements, record)
    log(f"{'ACCEPTED' if record['accepted'] else 'rejected'}: {record.get('hypothesis', '')[:80]} ({record['reason']})")
    return record
