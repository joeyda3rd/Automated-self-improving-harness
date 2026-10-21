"""The benchmark that gates self-improvement.

Each eval lives in evals/tasks/<name>/:
  task.json   {"title", "spec", "acceptance": [...], "verify_cmd": "..."}  what the builder sees
  seed/       optional starting repository contents
  check.sh    hidden acceptance test, run in the workspace after the session ends

The builder never sees check.sh (the guard hides evals/), so a harness change can
only score better by building better software, not by learning the answers.
"""
import glob
import os
import shutil
import subprocess
import tempfile
import time

from . import gitops
from .claude import BUILD_SCHEMA, BudgetExceeded, run_session
from .config import append_jsonl, load_json
from .tasks import card


def discover(harness):
    return sorted(d for d in glob.glob(os.path.join(harness.evals_dir, "*"))
                  if os.path.exists(os.path.join(d, "task.json")) and os.path.exists(os.path.join(d, "check.sh")))


def run_one(harness, eval_dir, plugin_dir, label, repeat=0):
    name = os.path.basename(eval_dir)
    spec = load_json(os.path.join(eval_dir, "task.json"), {})
    tmp = tempfile.mkdtemp(prefix=f"ash-eval-{name}-")
    ws = os.path.join(tmp, "ws")
    seed = os.path.join(eval_dir, "seed")
    shutil.copytree(seed, ws) if os.path.isdir(seed) else os.makedirs(ws)
    gitops.ensure_repo(ws)
    run_dir = os.path.join(harness.state, "evals", label, f"{name}-{repeat}")
    task = {"id": f"EVAL-{name}", "title": spec.get("title", name), "spec": spec.get("spec", ""),
            "acceptance": spec.get("acceptance", []), "history": []}
    res = run_session(harness, prompt="Work this task with the ash:build-task skill.\n\n" + card(task),
                      role="builder", cwd=ws, run_dir=run_dir, schema=BUILD_SCHEMA, plugin_dir=plugin_dir,
                      budget_usd=harness.get("eval_budget_usd_per_task", 2.0),
                      extra_env={"ASH_ROLE": "eval", "ASH_VERIFY_CMD": spec.get("verify_cmd", ""),
                                 "ASH_LESSONS": harness.learnings})
    try:
        check = subprocess.run(["bash", os.path.join(eval_dir, "check.sh")], cwd=ws,
                               capture_output=True, text=True, timeout=600)
        passed, detail = check.returncode == 0, (check.stdout + check.stderr)[-1000:]
    except subprocess.TimeoutExpired:
        passed, detail = False, "check timed out"
    shutil.rmtree(tmp, ignore_errors=True)
    return {"eval": name, "repeat": repeat, "passed": passed, "cost_usd": res.cost_usd,
            "turns": res.turns, "seconds": res.seconds, "detail": detail}


def run_suite(harness, plugin_dir, label, names=None):
    """Score a plugin directory (current harness or a candidate) on the evals named (default: all)."""
    results, incomplete = [], False
    for eval_dir in discover(harness):
        if names is not None and os.path.basename(eval_dir) not in names:
            continue
        for r in range(int(harness.get("eval_repeats", 1))):
            try:
                results.append(run_one(harness, eval_dir, plugin_dir, label, r))
            except BudgetExceeded:
                incomplete = True
                break
        if incomplete:
            break
    summary = summarize(label, results)
    summary["incomplete"] = incomplete  # cut short by the total budget: never cache or accept on it
    append_jsonl(os.path.join(harness.state, "eval_runs.jsonl"), summary)
    return summary


def summarize(label, results):
    n = len(results) or 1
    per_task = {}
    for r in results:
        t = per_task.setdefault(r["eval"], {"runs": 0, "passes": 0, "cost_usd": 0.0})
        t["runs"] += 1
        t["passes"] += int(r["passed"])
        t["cost_usd"] += r["cost_usd"]
    for t in per_task.values():
        t["rate"] = round(t["passes"] / t["runs"], 4)
        t["cost_usd"] = round(t["cost_usd"] / t["runs"], 4)
    return {
        "label": label, "ts": time.time(), "n": len(results),
        "pass_rate": round(sum(r["passed"] for r in results) / n, 4),
        "cost_usd": round(sum(r["cost_usd"] for r in results) / n, 4),
        "turns": round(sum(r["turns"] for r in results) / n, 2),
        "per_task": per_task,
        "results": results,
    }


def smoke_set(harness):
    """Evals marked {"smoke": true}: a cheap first stage that rejects obvious regressions."""
    return {os.path.basename(d) for d in discover(harness)
            if (load_json(os.path.join(d, "task.json"), {}) or {}).get("smoke")}


def regressions(baseline, candidate):
    """Evals the candidate does worse on than the baseline (paired, per task)."""
    return sorted(name for name, c in candidate["per_task"].items()
                  if name in baseline["per_task"] and c["rate"] < baseline["per_task"][name]["rate"])


def better(baseline, candidate, min_cost_gain=0.05):
    """The ratchet, paired per task. Returns (accepted, reason).

    LLM runs are noisy and a pooled pass rate hides which tasks moved, so the
    candidate is compared task by task on the evals both ran:
      - more tasks improved than regressed (and net gain > 0) => keep;
      - otherwise, only with no task changed: keep if mean cost fell by at least
        `min_cost_gain` AND the candidate was cheaper on most tasks;
      - anything else is discarded.
    """
    if candidate.get("incomplete") or baseline.get("incomplete"):
        return False, "benchmark incomplete (total budget reached)"
    shared = [n for n in candidate["per_task"] if n in baseline["per_task"]]
    if not shared:
        return False, "no evals ran"
    delta = {n: candidate["per_task"][n]["rate"] - baseline["per_task"][n]["rate"] for n in shared}
    wins = [n for n, d in delta.items() if d > 0]
    losses = [n for n, d in delta.items() if d < 0]
    if len(wins) > len(losses) and sum(delta.values()) > 0:
        return True, f"improved on {wins}, regressed on {losses or 'none'}"
    if losses or wins:
        return False, f"improved on {wins or 'none'}, regressed on {losses}"
    base_cost = sum(baseline["per_task"][n]["cost_usd"] for n in shared) / len(shared)
    cand_cost = sum(candidate["per_task"][n]["cost_usd"] for n in shared) / len(shared)
    cheaper = sum(candidate["per_task"][n]["cost_usd"] < baseline["per_task"][n]["cost_usd"] for n in shared)
    if base_cost and cand_cost <= base_cost * (1 - min_cost_gain) and cheaper > len(shared) / 2:
        return True, f"same results, cost ${base_cost:.3f} -> ${cand_cost:.3f} (cheaper on {cheaper}/{len(shared)})"
    return False, (f"no measurable gain (same results, cost ${base_cost:.3f} -> ${cand_cost:.3f}, "
                   f"cheaper on {cheaper}/{len(shared)})")
