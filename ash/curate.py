"""Eval curation: the harness grows and sharpens its own benchmark.

Self-improvement is only as good as the yardstick, and a yardstick that saturates (every
version passes) or turns noisy stops the loop. This module automates the pipeline that
builds discriminating, fair evals from real bug fixes in the projects listed in
evals/sources.json:

  mine    find commits whose tests fail on the parent and pass with the fix
  make    turn candidates into eval skeletons (pinned seed, hidden tests, reference) and validate
  report  a reporter session writes the user-style bug report, full and narrow
  screen  run new evals against the current harness (2 runs each)
  audit   an auditor session judges each failure fair or unfair; unfair narrow variants go
  gate    rebuild state/gate.json: audited-fair failures (minus noisy evals) + passing canaries

The reporter and auditor prompts live in ash/prompts (kernel): the improver cannot touch
how its own exam is written or graded.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from . import evals, gitops
from .claude import run_session
from .config import append_jsonl, load_json, read_jsonl, save_json

BUG_SUBJECT = re.compile(r"\b(fix|bug|crash|error|wrong|incorrect|regress|handle|preserve|reject|respect|"
                         r"broken|drop|lost|missing|escape|honou?r)", re.I)
NOT_A_BUG = re.compile(r"^\s*(feat|perf|refactor|docs?|tests?|chore|ci|build|style|bump|release)\b", re.I)

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "skip": {"type": "string"},
        "full": {"type": "object", "properties": {
            "title": {"type": "string"}, "spec": {"type": "string"},
            "acceptance": {"type": "array", "items": {"type": "string"}}}},
        "narrow": {"type": ["object", "null"], "properties": {
            "title": {"type": "string"}, "spec": {"type": "string"},
            "acceptance": {"type": "array", "items": {"type": "string"}}}},
    },
}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["fair", "unfair", "mixed"]},
        "failing_tests": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}


def log(msg):
    print(f"[ash curate {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sources(harness):
    return load_json(os.path.join(harness.home, "evals", "sources.json"), {}) or {}


def curation_dir(harness):
    return os.path.join(harness.state, "curation")


def gate_path(harness):
    return os.path.join(os.path.dirname(harness.evals_dir), "gate.json")  # versioned with the evals


# ------------------------------------------------------------------------------ mine

UPSTREAM = "refs/ash/upstream"


def clone(harness, src):
    """A local repository holding the upstream default branch's history at UPSTREAM.

    Shares state/repos/ with the eval runner's seed cache (which may hold only single
    fetched commits and no HEAD), so it always fetches into its own ref.
    """
    path = os.path.join(harness.state, "repos", "__".join(src["url"].rstrip("/").split("/")[-2:]))
    if not os.path.isdir(os.path.join(path, ".git")):
        os.makedirs(path, exist_ok=True)
        gitops.git(path, "init", "-q")
        gitops.git(path, "remote", "add", "origin", src["url"])
    gitops.git(path, "fetch", "-q", f"--depth={src.get('history', 1500)}", "origin", f"+HEAD:{UPSTREAM}")
    return path


def _export(repo, rev, paths, dest, prepare):
    present = [p for p in paths if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{rev}:{p}"],
                                                  capture_output=True).returncode == 0]
    os.makedirs(dest, exist_ok=True)
    tar = subprocess.run(["git", "-C", repo, "archive", rev, *present], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=tar, check=True)
    if prepare:
        subprocess.run(["bash", prepare], cwd=dest, check=True, capture_output=True)


def _overlay(repo, rev, files, dest):
    for f in files:
        target = os.path.join(dest, f)
        p = subprocess.run(["git", "-C", repo, "show", f"{rev}:{f}"], capture_output=True)
        if p.returncode != 0:
            if os.path.exists(target):
                os.remove(target)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(p.stdout)


def _passes(cmd, cwd, timeout=600):
    try:
        return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def prepare_script(harness, src):
    return os.path.join(harness.home, "evals", "prepare", src["prepare"]) if src.get("prepare") else None


def known_shas(harness):
    shas = set()
    for d in evals.discover(harness):
        pinned = load_json(os.path.join(d, "seed.git.json"))
        if pinned and pinned.get("fix"):
            shas.add(pinned["fix"][:10])
    for f in os.listdir(curation_dir(harness)) if os.path.isdir(curation_dir(harness)) else []:
        if f.endswith(".jsonl"):
            shas |= {r["sha"][:10] for r in read_jsonl(os.path.join(curation_dir(harness), f))}
    return shas


def mine(harness, name, limit=10, max_commits=1500, max_src_files=4):
    """Append up to `limit` new usable bug-fix commits of source `name` to state/curation/<name>.jsonl."""
    src = sources(harness)[name]
    repo = clone(harness, src)
    seen = known_shas(harness)
    out = os.path.join(curation_dir(harness), f"{name}.jsonl")
    found = 0
    for line in gitops.git(repo, "log", "--format=%H|%cs|%s", "--no-merges", "-n", str(max_commits),
                           UPSTREAM, "--", src["src"], src["tests"]).splitlines():
        sha, date, subject = line.split("|", 2)
        if sha[:10] in seen or NOT_A_BUG.search(subject) or not BUG_SUBJECT.search(subject):
            continue
        files = gitops.git(repo, "diff", "--name-only", f"{sha}^", sha, check=False).split()
        srcs = [f for f in files if f.startswith(src["src"]) and f.endswith(".py")]
        tests = [f for f in files if f.startswith(src["tests"])]
        if not srcs or not tests or len(srcs) > max_src_files:
            continue
        tmp = tempfile.mkdtemp(prefix="ash-mine-")
        try:
            _export(repo, f"{sha}^", src["paths"], tmp, prepare_script(harness, src))
            if not _passes(src["test_cmd"], tmp):
                continue  # the parent must be green
            _overlay(repo, sha, tests, tmp)
            if _passes(src["test_cmd"], tmp):
                continue  # the fix's tests must expose the bug
            _overlay(repo, sha, srcs, tmp)
            if not _passes(src["test_cmd"], tmp):
                continue
            append_jsonl(out, {"sha": sha, "date": date, "subject": subject, "source": name,
                               "src": srcs, "tests": tests, "state": "mined"})
            found += 1
            log(f"{name}: {sha[:10]} {subject[:60]}")
            if found >= limit:
                break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return found


# ------------------------------------------------------------------------------ make

def slug(subject):
    words = re.sub(r"\(#?\d+\)|#\d+|[^a-z0-9 ]+", " ", subject.lower()).split()
    words = [w for w in words if w not in {"fix", "fixes", "fixed", "the", "a", "an", "of", "in", "to", "for",
                                           "and", "when", "with", "on", "issue"}]
    return "-".join(words[:4]) or "bug"


def validate(harness, eval_dir):
    """True when the eval fails on its seed and passes with its reference laid over the seed."""
    outcomes = []
    for overlay in (False, True):
        tmp = tempfile.mkdtemp(prefix="ash-validate-")
        ws = os.path.join(tmp, "ws")
        try:
            evals.lay_seed(harness.state, eval_dir, ws)
            if overlay:
                shutil.copytree(os.path.join(eval_dir, "reference"), ws, dirs_exist_ok=True)
            outcomes.append(evals.run_check(eval_dir, ws, timeout=900)[0])
        except subprocess.CalledProcessError:
            outcomes.append(None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return outcomes == [False, True]


def _set_state(harness, name, sha, **fields):
    path = os.path.join(curation_dir(harness), f"{name}.jsonl")
    rows = read_jsonl(path)
    for r in rows:
        if r["sha"] == sha:
            r.update(fields)
    with open(path, "w") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in rows))


def make(harness, name, limit=10):
    """Turn mined candidates into validated eval skeletons; the report is written later."""
    src = sources(harness)[name]
    repo = clone(harness, src)
    made = []
    for cand in [r for r in read_jsonl(os.path.join(curation_dir(harness), f"{name}.jsonl"))
                 if r.get("state") == "mined"][:limit]:
        sha = cand["sha"]
        eval_name = f"{src['prefix']}-{slug(cand['subject'])}"
        out = os.path.join(harness.evals_dir, eval_name)
        if os.path.exists(out):
            eval_name += "-" + sha[:6]
            out = os.path.join(harness.evals_dir, eval_name)
        os.makedirs(out)
        parent = gitops.git(repo, "rev-parse", f"{sha}^")
        paths = [p for p in src["paths"] if subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{parent}:{p}"],
                                                           capture_output=True).returncode == 0]
        save_json(os.path.join(out, "seed.git.json"), {"url": src["url"], "rev": parent, "paths": paths, "fix": sha})
        _overlay(repo, sha, cand["tests"], os.path.join(out, "hidden"))
        _overlay(repo, sha, cand["src"], os.path.join(out, "reference"))
        if src.get("prepare"):
            shutil.copyfile(prepare_script(harness, src), os.path.join(out, "prepare.sh"))
        with open(os.path.join(out, "check.sh"), "w") as fh:
            fh.write("set -e\n# the fix commit's own tests (hidden) over the builder's work, then the whole suite\n"
                     'cp -r "$ASH_EVAL_DIR/hidden/." .\n'
                     f"{src['test_cmd']} 2>&1 | tail -20\nexit ${{PIPESTATUS[0]}}\n")
        save_json(os.path.join(out, "task.json"), {
            "title": "", "spec": "", "acceptance": [], "verify_cmd": src["test_cmd"],
            "source": f"{src['url']}/commit/{sha}", "curation": {"state": "unreported", "source": name}})
        if validate(harness, out):
            made.append(eval_name)
            _set_state(harness, name, sha, state="made", eval=eval_name)
            log(f"made {eval_name}")
        else:
            shutil.rmtree(out, ignore_errors=True)
            _set_state(harness, name, sha, state="invalid")
            log(f"dropped {eval_name}: did not validate here")
    return made


# ---------------------------------------------------------------------------- report

def _curation(d):
    return (load_json(os.path.join(d, "task.json"), {}) or {}).get("curation", {})


def report(harness, limit=10):
    """Write full and narrow reports for evals made but not yet reported."""
    done = []
    for d in [d for d in evals.discover(harness) if _curation(d).get("state") == "unreported"][:limit]:
        task = load_json(os.path.join(d, "task.json"))
        src = sources(harness)[task["curation"]["source"]]
        tmp = tempfile.mkdtemp(prefix="ash-report-")
        buggy, fixed = os.path.join(tmp, "buggy"), os.path.join(tmp, "fixed")
        evals.lay_seed(harness.state, d, buggy)
        evals.lay_seed(harness.state, d, fixed)
        shutil.copytree(os.path.join(d, "reference"), fixed, dirs_exist_ok=True)
        prompt = (f"Write the bug reports for this eval. Intro line to start each spec with:\n{src['intro']}\n\n"
                  f"Buggy code: the current directory. Fixed code: {fixed}. Hidden tests: {d}/hidden. "
                  f"Upstream fix commit: {load_json(os.path.join(d, 'seed.git.json'))['fix']} "
                  f"(do not mention it in the report).")
        res = run_session(harness, prompt=prompt, role="reporter", cwd=buggy,
                          run_dir=os.path.join(harness.state, "curation", "runs", os.path.basename(d) + "-report"),
                          schema=REPORT_SCHEMA, budget_usd=harness.get("curate_report_budget_usd", 1.5),
                          extra_env={"ASH_WRITE_ROOTS": tmp})
        shutil.rmtree(tmp, ignore_errors=True)
        out = res.output
        full = out.get("full") or {}
        if out.get("skip") or not full.get("spec"):
            log(f"{os.path.basename(d)}: skipped ({out.get('skip') or 'no report'})")
            shutil.rmtree(d, ignore_errors=True)
            continue
        task.update({k: full.get(k) for k in ("title", "spec", "acceptance")})
        task["curation"]["state"] = "reported"
        save_json(os.path.join(d, "task.json"), task)
        done.append(os.path.basename(d))
        narrow = out.get("narrow")
        if narrow and narrow.get("spec"):
            nd = d + "-narrow"
            shutil.copytree(d, nd)
            ntask = dict(task, **{k: narrow.get(k) for k in ("title", "spec", "acceptance")})
            ntask["curation"] = dict(task["curation"], narrow_of=os.path.basename(d))
            save_json(os.path.join(nd, "task.json"), ntask)
            done.append(os.path.basename(nd))
        log(f"reported {os.path.basename(d)}{' (+ narrow)' if narrow else ''}")
    return done


# ---------------------------------------------------------------------------- screen

def screen(harness, repeats=2):
    """Run every reported-but-unscreened eval against the current harness."""
    names = {os.path.basename(d) for d in evals.discover(harness) if _curation(d).get("state") == "reported"}
    if not names:
        return None
    summary = evals.run_suite(harness, harness.plugin_dir, f"screen-{time.strftime('%Y%m%d-%H%M%S')}",
                              names=names, repeats=repeats, resumable=True)
    if summary.get("incomplete"):
        return summary
    for name, t in summary["per_task"].items():
        d = os.path.join(harness.evals_dir, name)
        task = load_json(os.path.join(d, "task.json"))
        task["curation"].update(state="screened", screen_rate=t["rate"], screen_label=summary["label"])
        save_json(os.path.join(d, "task.json"), task)
    return summary


# ----------------------------------------------------------------------------- audit

def audit(harness, limit=10):
    """Judge each screened failure fair or unfair. Unfair narrow variants are removed."""
    verdicts = {}
    todo = [d for d in evals.discover(harness)
            if _curation(d).get("state") == "screened" and _curation(d).get("screen_rate", 1) < 1][:limit]
    for d in todo:
        name = os.path.basename(d)
        task = load_json(os.path.join(d, "task.json"))
        label = task["curation"]["screen_label"]
        runs = sorted(os.path.join(harness.state, "evals", label, x)
                      for x in os.listdir(os.path.join(harness.state, "evals", label)) if x.startswith(name + "-")
                      and x[len(name) + 1:].isdigit())
        results = [r for s in read_jsonl(os.path.join(harness.state, "eval_runs.jsonl")) if s.get("label") == label
                   for r in s.get("results", []) if r["eval"] == name]
        tmp = tempfile.mkdtemp(prefix="ash-audit-")
        prompt = (f"Audit the failures of eval {name}. Eval directory: {d}. Builder runs: {', '.join(runs)}. "
                  "Hidden-check output (tail) per run:\n"
                  + "\n---\n".join(r.get("detail", "")[-800:] for r in results if not r.get("passed")))
        res = run_session(harness, prompt=prompt, role="auditor", cwd=tmp,
                          run_dir=os.path.join(harness.state, "curation", "runs", name + "-audit"),
                          schema=AUDIT_SCHEMA, budget_usd=harness.get("curate_audit_budget_usd", 2.0),
                          extra_env={"ASH_WRITE_ROOTS": tmp})
        shutil.rmtree(tmp, ignore_errors=True)
        verdict = res.output.get("verdict", "unfair")  # no verdict, no gate
        verdicts[name] = verdict
        if verdict != "fair" and task["curation"].get("narrow_of"):
            shutil.rmtree(d, ignore_errors=True)
            log(f"{name}: {verdict}, removed ({res.output.get('reason', '')[:100]})")
            continue
        task["curation"].update(state="audited", verdict=verdict, reason=res.output.get("reason", ""))
        save_json(os.path.join(d, "task.json"), task)
        log(f"{name}: {verdict}")
    for d in evals.discover(harness):  # screened evals that passed need no audit
        if _curation(d).get("state") == "screened" and _curation(d).get("screen_rate", 0) >= 1:
            task = load_json(os.path.join(d, "task.json"))
            task["curation"].update(state="audited", verdict="passing")
            save_json(os.path.join(d, "task.json"), task)
    return verdicts


# ------------------------------------------------------------------------------ gate

def regate(harness, canaries_per_source=1):
    """Gate = audited-fair failures that are not noisy, plus one passing canary per source (smoke)."""
    noisy = evals.noisy_evals(harness)
    fair, canaries = [], {}
    for d in evals.discover(harness):
        c, name = _curation(d), os.path.basename(d)
        if c.get("verdict") == "fair" and name not in noisy:
            fair.append(name)
        elif c.get("verdict") == "passing" and c.get("narrow_of"):
            canaries.setdefault(c.get("source"), []).append(name)
    smoke = sorted(n for names in canaries.values() for n in sorted(names)[:canaries_per_source])
    previous = load_json(gate_path(harness), {}) or {}
    gate = {"updated": time.time(), "gate": sorted(set(fair) | set(previous.get("gate", [])) - noisy),
            "smoke": sorted(set(smoke) | set(previous.get("smoke", []))), "noisy": sorted(noisy)}
    save_json(gate_path(harness), gate)
    return gate


def needs_growth(harness):
    """Too few discriminating evals for improvement cycles to carry signal."""
    gate = load_json(gate_path(harness), {}) or {}
    return len(gate.get("gate", [])) < harness.get("min_gate_discriminating", 8)


def grow(harness, per_source=3):
    """One full curation pass across all sources: mine -> make -> report -> screen -> audit -> gate."""
    for name in sources(harness):
        mine(harness, name, limit=per_source)
        make(harness, name, limit=per_source)
    report(harness)
    screen(harness)
    audit(harness)
    gate = regate(harness)
    if gitops.is_repo(harness.home):  # the benchmark is versioned: commit what curation added or removed
        gitops.git(harness.home, "add", "-A", "evals")
        if gitops.git(harness.home, "diff", "--cached", "--name-only", "--", "evals"):
            gitops.git(harness.home, "-c", "user.name=ASH", "-c", "user.email=ash@localhost", "commit", "-q",
                       "-m", f"ASH curation: gate now {len(gate['gate'])} discriminating + {len(gate['smoke'])} smoke",
                       "--", "evals")
    return gate
