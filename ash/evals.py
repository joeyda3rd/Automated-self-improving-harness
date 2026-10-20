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
from .claude import BUILD_SCHEMA, run_session
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


def run_suite(harness, plugin_dir, label):
    """Score a plugin directory (current harness or a candidate) on every eval."""
    results = []
    for eval_dir in discover(harness):
        for r in range(int(harness.get("eval_repeats", 1))):
            results.append(run_one(harness, eval_dir, plugin_dir, label, r))
    n = len(results) or 1
    summary = {
        "label": label, "ts": time.time(), "n": len(results),
        "pass_rate": round(sum(r["passed"] for r in results) / n, 4),
        "cost_usd": round(sum(r["cost_usd"] for r in results) / n, 4),
        "turns": round(sum(r["turns"] for r in results) / n, 2),
        "results": results,
    }
    append_jsonl(os.path.join(harness.state, "eval_runs.jsonl"), summary)
    return summary


def better(baseline, candidate, min_cost_gain=0.05):
    """The ratchet. Returns (accepted, reason)."""
    if candidate["n"] == 0:
        return False, "no evals ran"
    if candidate["pass_rate"] > baseline["pass_rate"]:
        return True, f"pass rate {baseline['pass_rate']:.0%} -> {candidate['pass_rate']:.0%}"
    if candidate["pass_rate"] < baseline["pass_rate"]:
        return False, f"pass rate dropped {baseline['pass_rate']:.0%} -> {candidate['pass_rate']:.0%}"
    if baseline["cost_usd"] and candidate["cost_usd"] <= baseline["cost_usd"] * (1 - min_cost_gain):
        return True, f"same pass rate, cost ${baseline['cost_usd']:.3f} -> ${candidate['cost_usd']:.3f}"
    return False, (f"no measurable gain (pass {candidate['pass_rate']:.0%}, "
                   f"cost ${baseline['cost_usd']:.3f} -> ${candidate['cost_usd']:.3f})")
