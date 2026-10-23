"""The benchmark that gates self-improvement.

Each eval lives in evals/tasks/<name>/:
  task.json   {"title", "spec", "acceptance": [...], "verify_cmd": "..."}  what the builder sees
  seed/       optional starting repository contents, or instead
  seed.git.json  {"url", "rev", "paths": [...]}: export of a pinned commit of a public repo
                 (fetched once into state/repos/), for evals built from real projects
  prepare.sh  optional, run in the fresh workspace after the seed is laid down
  check.sh    hidden acceptance test, run in the workspace after the session ends,
              with $ASH_EVAL_DIR pointing at the eval (e.g. for hidden test files)

The builder never sees check.sh (the guard hides evals/), so a harness change can
only score better by building better software, not by learning the answers.
"""
import glob
import os
import shutil
import subprocess
import tempfile
import threading
import time

from . import gitops
from .claude import BUILD_SCHEMA, BudgetExceeded, run_session
from .config import append_jsonl, load_json, read_jsonl, save_json
from .tasks import card


def discover(harness):
    return sorted(d for d in glob.glob(os.path.join(harness.evals_dir, "*"))
                  if os.path.exists(os.path.join(d, "task.json")) and os.path.exists(os.path.join(d, "check.sh")))


def _repo_cache(state, url, rev):
    """A local clone of `url` holding `rev`, fetched once and reused."""
    path = os.path.join(state, "repos", url.rstrip("/").split("/")[-2] + "__" + url.rstrip("/").split("/")[-1])
    if not os.path.isdir(os.path.join(path, ".git")):
        os.makedirs(path, exist_ok=True)
        gitops.git(path, "init", "-q")
        gitops.git(path, "remote", "add", "origin", url)
    have = subprocess.run(["git", "-C", path, "cat-file", "-e", f"{rev}^{{commit}}"], capture_output=True)
    if have.returncode != 0:
        gitops.git(path, "fetch", "-q", "--depth=1", "origin", rev)
    return path


_cache_lock = threading.Lock()


def lay_seed(state, eval_dir, ws):
    """Create the eval's starting workspace: seed/ copy or pinned git export, then prepare.sh."""
    seed = os.path.join(eval_dir, "seed")
    pinned = load_json(os.path.join(eval_dir, "seed.git.json"))
    if pinned:
        with _cache_lock:  # parallel runs share one clone per repository
            repo = _repo_cache(state, pinned["url"], pinned["rev"])
        os.makedirs(ws)
        tar = subprocess.run(["git", "-C", repo, "archive", pinned["rev"], *pinned.get("paths", [])],
                             capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", ws], input=tar, check=True)
    elif os.path.isdir(seed):
        shutil.copytree(seed, ws)
    else:
        os.makedirs(ws)
    prepare = os.path.join(eval_dir, "prepare.sh")
    if os.path.exists(prepare):
        subprocess.run(["bash", prepare], cwd=ws, check=True, capture_output=True)


def run_check(eval_dir, ws, timeout=600):
    env = dict(os.environ, ASH_EVAL_DIR=os.path.abspath(eval_dir))
    try:
        check = subprocess.run(["bash", os.path.join(eval_dir, "check.sh")], cwd=ws, env=env,
                               capture_output=True, text=True, timeout=timeout)
        return check.returncode == 0, (check.stdout + check.stderr)[-1000:]
    except subprocess.TimeoutExpired:
        return False, "check timed out"


def run_one(harness, eval_dir, plugin_dir, label, repeat=0):
    name = os.path.basename(eval_dir)
    spec = load_json(os.path.join(eval_dir, "task.json"), {})
    tmp = tempfile.mkdtemp(prefix=f"ash-eval-{name}-")
    ws = os.path.join(tmp, "ws")
    lay_seed(harness.state, eval_dir, ws)
    gitops.ensure_repo(ws)
    run_dir = os.path.join(harness.state, "evals", label, f"{name}-{repeat}")
    task = {"id": f"EVAL-{name}", "title": spec.get("title", name), "spec": spec.get("spec", ""),
            "acceptance": spec.get("acceptance", []), "history": []}
    res = run_session(harness, prompt="Work this task with the ash:build-task skill.\n\n" + card(task),
                      role="builder", cwd=ws, run_dir=run_dir, schema=BUILD_SCHEMA, plugin_dir=plugin_dir,
                      budget_usd=harness.get("eval_budget_usd_per_task", 2.0),
                      extra_env={"ASH_ROLE": "eval", "ASH_VERIFY_CMD": spec.get("verify_cmd", ""),
                                 "ASH_LESSONS": harness.learnings})
    passed, detail = run_check(eval_dir, ws)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"eval": name, "repeat": repeat, "passed": passed, "cost_usd": res.cost_usd, "run_dir": run_dir,
            "title": spec.get("title", name),
            "turns": res.turns, "seconds": res.seconds, "detail": detail}


def gate_set(harness):
    """The evals that decide self-improvements: `improve_evals` glob patterns (default: all).

    Evals every harness version passes carry no signal and only cost money, so the gate can
    be pointed at the discriminating ones (e.g. real-bug evals) while the rest stay runnable.
    """
    import fnmatch
    patterns = harness.get("improve_evals", ["*"])
    names = {os.path.basename(d) for d in discover(harness)}
    gate = set()
    for p in patterns:
        if p == "@gate":  # the curated gate (evals/gate.json): discriminating evals plus smoke canaries
            g = load_json(os.path.join(os.path.dirname(harness.evals_dir), "gate.json"), {}) or {}
            gate |= (set(g.get("gate", [])) | set(g.get("smoke", []))) & names
        else:
            gate |= {n for n in names if fnmatch.fnmatch(n, p)}
    return gate


def run_suite(harness, plugin_dir, label, names=None, repeats=None, resumable=False):
    """Score a plugin directory (current harness or a candidate) on the evals named (default: all).

    With resumable=True each finished run is saved under state/eval_results/<label>/ and reused
    if the suite is started again with the same label, so an interrupted benchmark (a container
    restart) only pays for the runs it had not finished. Only use it when the label pins the
    exact plugin being measured, e.g. a baseline keyed by harness commit.
    """
    from concurrent.futures import ThreadPoolExecutor

    jobs = [(d, r) for d in discover(harness) if names is None or os.path.basename(d) in names
            for r in range(int(repeats or harness.get("eval_repeats", 1)))]
    results, incomplete = [], False

    def one(job):
        nonlocal incomplete
        if incomplete:
            return None
        try:
            if not resumable:
                return run_one(harness, job[0], plugin_dir, label, job[1])
            saved = os.path.join(harness.state, "eval_results", label, f"{os.path.basename(job[0])}-{job[1]}.json")
            if os.path.exists(saved):
                return load_json(saved)
            result = run_one(harness, job[0], plugin_dir, label, job[1])
            save_json(saved, result)
            return result
        except BudgetExceeded:
            incomplete = True
            return None

    # Sessions are independent (own workspace, run dir and session id), so they run side by side;
    # the budget stays exact because each session reserves its cap before it starts.
    with ThreadPoolExecutor(max_workers=max(1, int(harness.get("eval_workers", 4)))) as pool:
        results = [r for r in pool.map(one, jobs) if r is not None]
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
    """Evals marked {"smoke": true} within the gate set: a cheap first stage that rejects obvious regressions."""
    curated = load_json(os.path.join(os.path.dirname(harness.evals_dir), "gate.json"), {}) or {}
    return ({os.path.basename(d) for d in discover(harness)
             if (load_json(os.path.join(d, "task.json"), {}) or {}).get("smoke")} | set(curated.get("smoke", []))) \
        & gate_set(harness)


def regressions(baseline, candidate):
    """Evals the candidate does worse on than the baseline (paired, per task)."""
    return sorted(name for name, c in candidate["per_task"].items()
                  if name in baseline["per_task"] and c["rate"] < baseline["per_task"][name]["rate"])


def noisy_evals(harness, low=0.15, high=0.85, min_runs=4):
    """Evals whose recorded outcomes are mixed: a swing on them is more likely noise than effect.

    Measured from every benchmark run in state/eval_runs.jsonl. An eval that always fails or always
    passes is informative at 2 runs; one that passes 40% of the time is not.
    """
    tally = {}
    for summary in read_jsonl(os.path.join(harness.state, "eval_runs.jsonl")):
        for r in summary.get("results", []):
            t = tally.setdefault(r["eval"], [0, 0])
            t[0] += 1
            t[1] += bool(r.get("passed"))
    return {name for name, (n, p) in tally.items() if n >= min_runs and low < p / n < high}


def better(baseline, candidate, min_cost_gain=0.05, noisy=(), noise_margin=0.75):
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
    # a swing on a noisy eval only counts when it is larger than its usual noise
    delta = {n: (0.0 if n in noisy and abs(d) < noise_margin else d) for n, d in delta.items()}
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
