"""The build loop: intake -> plan -> build (verify-gated) -> integrate -> retro -> improve."""
import glob
import os
import shutil
import subprocess
import time

from . import gitops, integrity
from . import claude
from .claude import BUILD_SCHEMA, PLAN_SCHEMA, RETRO_SCHEMA, BudgetExceeded, run_session
from .config import append_jsonl, load_json, read_jsonl, save_json
from .memory import add_lessons, curate, injected, read_lessons
from .tasks import ACTIVE, BLOCKED, DONE, FAILED, PENDING, TaskStore, card


def log(msg):
    print(f"[ash {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def verify(cmd, cwd, timeout=900):
    """Run the project's verification command. No command means nothing to check."""
    if not cmd:
        return True, "(no verify_cmd configured)"
    try:
        proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        return False, f"verification timed out after {timeout}s"


def new_run_dir(harness, label):
    path = os.path.join(harness.runs_dir, f"{time.strftime('%Y%m%d-%H%M%S')}-{label}")
    n, base = 1, path
    while os.path.exists(path):
        n, path = n + 1, f"{base}-{n}"
    os.makedirs(path)
    return path


def harness_commit(harness):
    try:
        return gitops.head(harness.home)[:12] if gitops.is_repo(harness.home) else ""
    except gitops.GitError:
        return ""


def run_stats(run_dir):
    """Telemetry the kernel hooks wrote during the run."""
    tools = read_jsonl(os.path.join(run_dir, "tools.jsonl"))
    gate = read_jsonl(os.path.join(run_dir, "gate.jsonl"))
    return {
        "tool_calls": len(tools),
        "tool_errors": sum(1 for t in tools if t.get("error")),
        "gate_failures": sum(1 for g in gate if not g.get("passed")),
        "guard_denials": len(read_jsonl(os.path.join(run_dir, "guard.jsonl"))),
    }


def write_status(harness, project, state, current=None, note=""):
    store = TaskStore(project)
    status = {
        "updated": time.time(),
        "state": state,
        "current": current,
        "note": note,
        "counts": store.counts(),
        "harness": {
            "commit": harness_commit(harness),
            "lessons": len(read_lessons(harness.learnings)),
            "improvements": [
                {k: r.get(k) for k in ("ts", "accepted", "hypothesis", "reason")}
                for r in read_jsonl(harness.improvements)[-5:]
            ],
        },
        "recent": [
            {k: r.get(k) for k in ("task", "title", "outcome", "cost_usd", "turns")}
            for r in read_jsonl(harness.metrics)[-8:] if r.get("kind") == "build"
        ],
    }
    save_json(os.path.join(project.ash, "status.json"), status)
    save_json(os.path.join(harness.state, "status.json"), dict(status, project=project.root))


# -------------------------------------------------------------------- init/intake

PROJECT_GITIGNORE = "tasks/\nworktrees/\ninbox/\nstatus.json\nproject.json\n"


def init_project(project, verify_cmd=None, base_branch=None):
    os.makedirs(project.ash, exist_ok=True)
    branch = base_branch or project.config.get("base_branch") or "main"
    gitops.ensure_repo(project.root, branch)
    branch = base_branch or gitops.current_branch(project.root)
    for d in (project.tasks_dir, project.inbox, project.worktrees):
        os.makedirs(d, exist_ok=True)
    gi = os.path.join(project.ash, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w") as fh:
            fh.write(PROJECT_GITIGNORE)
    project.set_config(base_branch=branch, verify_cmd=verify_cmd)
    gitops.commit_all(project.root, "ASH: initialise project state")


def intake_inbox(project):
    """Every markdown file dropped into .ash/inbox/ becomes a planning assignment."""
    store = TaskStore(project)
    added = []
    for path in sorted(glob.glob(os.path.join(project.inbox, "*.md"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
        title = text.splitlines()[0].lstrip("# ").strip() if text else os.path.basename(path)
        added.append(store.add(title, text, kind="plan", priority=2, source=f"inbox:{os.path.basename(path)}"))
        done_dir = os.path.join(project.inbox, "processed")
        os.makedirs(done_dir, exist_ok=True)
        shutil.move(path, os.path.join(done_dir, f"{int(time.time())}-{os.path.basename(path)}"))
    return added


# --------------------------------------------------------------------------- plan

def plan(harness, project, task):
    store = TaskStore(project)
    run_dir = new_run_dir(harness, f"{task['id']}-plan")
    save_json(os.path.join(run_dir, "task.json"), task)
    prompt = (
        "Plan this assignment for the repository in the current directory using the ash:plan-work skill.\n\n"
        f"Current verification command: `{project.verify_cmd or '(none yet)'}`\n\n{card(task)}"
    )
    res = run_session(harness, prompt=prompt, role="planner", cwd=project.root, run_dir=run_dir,
                      schema=PLAN_SCHEMA, budget_usd=harness.get("budget_usd_per_run"),
                      extra_env={"ASH_WRITE_ROOTS": "/dev/null", "ASH_LESSONS": lessons_env(harness, project)})
    planned = res.output.get("tasks") or []
    if not res.ok or not planned:
        return finish(harness, project, task, run_dir, FAILED, res, note=res.error or "planner produced no tasks")
    if res.output.get("verify_cmd") and not project.verify_cmd:
        project.set_config(verify_cmd=res.output["verify_cmd"])
    ids = []
    for item in planned:
        deps = [ids[i] for i in item.get("depends_on", []) if isinstance(i, int) and 0 <= i < len(ids)]
        child = store.add(item["title"], item.get("spec", ""), acceptance=item.get("acceptance"),
                          depends_on=deps, priority=item.get("priority", 3), parent=task["id"], source="planner")
        ids.append(child["id"])
    log(f"{task['id']} planned into {len(ids)} tasks: {', '.join(ids)}")
    return finish(harness, project, task, run_dir, DONE, res, note=f"planned {len(ids)} tasks")


# -------------------------------------------------------------------------- build

def lessons_env(harness, project):
    return ":".join([harness.learnings, project.lessons_path(harness)])


def build(harness, project, task):
    """Work one task in its own worktree until verification passes, then integrate it."""
    store = TaskStore(project)
    run_dir = new_run_dir(harness, task["id"])
    save_json(os.path.join(run_dir, "task.json"), task)
    branch = f"ash/{task['id']}"
    wt = os.path.join(project.worktrees, task["id"])
    base = project.base_branch
    gitops.add_worktree(project.root, wt, branch, base)

    env = {"ASH_VERIFY_CMD": project.verify_cmd, "ASH_LESSONS": lessons_env(harness, project)}
    given = injected(lessons_env(harness, project).split(":"))
    prompt = ("Work this task with the ash:build-task skill. The current directory is your worktree.\n\n"
              + card(task))
    session, total = None, None
    outcome, note = FAILED, ""
    for attempt in range(1, int(harness.get("max_attempts_per_run", 2)) + 1):
        res = run_session(harness, prompt=prompt, role="builder", cwd=wt, run_dir=run_dir,
                          schema=BUILD_SCHEMA, resume=session, extra_env=env,
                          budget_usd=harness.get("budget_usd_per_run"))
        total = _accumulate(total, res)
        session = res.session_id
        status = res.output.get("status")
        if status == "blocked":
            outcome, note = BLOCKED, res.output.get("summary", "")
            break
        if not res.ok and not res.output:
            outcome, note = FAILED, res.error or "session failed"
            break
        ok, output = verify(project.verify_cmd, wt, harness.get("verify_timeout_seconds", 900))
        if ok and status == "done":
            outcome, note = DONE, res.output.get("summary", "")
            break
        note = f"independent verification {'passed' if ok else 'failed'}, agent reported {status!r}:\n{output[-1500:]}"
        prompt = ("The orchestrator re-ran verification and the task is not done.\n\n" + note
                  + "\n\nFix it, then finish with the JSON result again.")
        log(f"{task['id']} attempt {attempt} not accepted; resuming session")

    if outcome == DONE:
        outcome, note = integrate(project, task, wt, branch, note, harness)

    follow_ups = (total.output.get("follow_ups") or []) if outcome == DONE else []
    for fu in follow_ups:
        if task.get("depth", 0) < 2:
            child = store.add(fu["title"], fu.get("spec", ""), priority=4, parent=task["id"], source="follow-up")
            child["depth"] = task.get("depth", 0) + 1
            store.save(child)
    gitops.remove_worktree(project.root, wt, branch)
    return finish(harness, project, task, run_dir, outcome, total, note=note, extra={"lessons": given})


def integrate(project, task, wt, branch, note, harness):
    """Commit, bring the latest base in, re-verify, merge. Base is only ever moved by a verified merge."""
    message = f"{task['id']}: {task['title']}\n\n{note[:2000]}\n\nBuilt by ASH."
    if not gitops.commit_all(wt, message):
        return FAILED, "agent reported done but changed nothing"
    problems = integrity.check(wt, project.base_branch)
    if problems and not integrity.allowed_by(task):
        return FAILED, ("test integrity: " + "; ".join(problems)
                        + ". Fix the code, not the tests; tests may only be removed or skipped if the task says so.")
    if not gitops.merge(wt, project.base_branch, f"Merge {project.base_branch} into {branch}"):
        return FAILED, "conflict with the latest base; redo on top of it"
    ok, output = verify(project.verify_cmd, wt, harness.get("verify_timeout_seconds", 900))
    if not ok:
        return FAILED, "verification failed after merging the latest base:\n" + output[-1500:]
    if gitops.current_branch(project.root) != project.base_branch:
        return FAILED, f"project checkout is not on {project.base_branch}; cannot integrate"
    if not gitops.merge(project.root, branch, f"Merge {branch}: {task['title']}"):
        return FAILED, "merge into base failed (uncommitted changes in the project checkout?)"
    return DONE, note


def _accumulate(total, res):
    if total is None:
        return res
    total.cost_usd += res.cost_usd
    total.turns += res.turns
    total.seconds += res.seconds
    total.ok, total.output, total.error = res.ok, res.output, res.error
    return total


def finish(harness, project, task, run_dir, outcome, res, note="", extra=None):
    """Record the outcome on the task, in the run directory and in the metrics ledger."""
    store = TaskStore(project)
    task = store.get(task["id"]) or task
    task["runs"] = task.get("runs", 0) + 1
    task["history"].append({"ts": time.time(), "event": "run", "outcome": outcome, "note": note[:2000],
                            "run_dir": run_dir})
    if outcome in (DONE, BLOCKED):
        task["status"] = outcome
    elif task["runs"] < int(harness.get("max_runs_per_task", 3)):
        task["status"] = PENDING  # retry later with the failure in the task card
    else:
        task["status"] = FAILED
    store.save(task)
    record = {
        "ts": time.time(), "kind": task.get("kind", "build"), "project": project.root,
        "task": task["id"], "title": task["title"], "outcome": outcome, "run": task["runs"],
        "cost_usd": round(res.cost_usd, 4) if res else 0.0, "turns": res.turns if res else 0,
        "seconds": res.seconds if res else 0, "harness_commit": harness_commit(harness),
        "run_dir": run_dir, "note": note[:300],
    }
    record.update(run_stats(run_dir))
    record.update(extra or {})
    save_json(os.path.join(run_dir, "result.json"), dict(record, output=res.output if res else {}))
    append_jsonl(harness.metrics, record)
    log(f"{task['id']} {task.get('kind', 'build')} -> {outcome} (${record['cost_usd']}, {record['turns']} turns)")
    return record


# -------------------------------------------------------------------------- retro

def retro(harness, project, record):
    """Fast loop: distil lessons from one run into memory injected at every session start."""
    run_dir = record["run_dir"]
    prompt = (f"Run the ash:retrospective skill on the run recorded in {run_dir} "
              f"(lessons the session was given: {', '.join(record.get('lessons', [])) or 'none'}) "
              f"(outcome: {record['outcome']}, cost ${record['cost_usd']}, {record['turns']} turns, "
              f"{record.get('gate_failures', 0)} stop-gate bounces, {record.get('tool_errors', 0)} tool errors).")
    res = run_session(harness, prompt=prompt, role="retro", cwd=run_dir, run_dir=os.path.join(run_dir, "retro"),
                      schema=RETRO_SCHEMA, budget_usd=min(1.0, harness.get("budget_usd_per_run", 5.0)),
                      extra_env={"ASH_WRITE_ROOTS": "retro"})
    lessons = res.output.get("lessons") or []
    cap = harness.get("learnings_max", 60)
    source = f"{record['task']}"
    added = add_lessons(harness.learnings, [l["text"] for l in lessons if l.get("scope") == "harness"], source, cap)
    added += add_lessons(project.lessons_path(harness), [l["text"] for l in lessons if l.get("scope") == "project"],
                         source, cap)
    for vote in res.output.get("lesson_feedback") or []:
        if vote.get("id") in record.get("lessons", []):
            append_jsonl(os.path.join(harness.state, "lesson_votes.jsonl"),
                         {"ts": time.time(), "task": record["task"], **vote})
    pruned = curate(harness, [harness.learnings, project.lessons_path(harness)])
    if res.output.get("harness_suggestion"):
        append_jsonl(os.path.join(harness.state, "suggestions.jsonl"),
                     {"ts": time.time(), "task": record["task"], "outcome": record["outcome"],
                      "suggestion": res.output["harness_suggestion"]})
    append_jsonl(harness.metrics, {"ts": time.time(), "kind": "retro", "task": record["task"],
                                   "cost_usd": round(res.cost_usd, 4), "lessons_added": len(added),
                                   "lessons_pruned": len(pruned)})
    return added


# --------------------------------------------------------------------------- loop

def spent(harness):
    return claude.spent(harness)


def builds_since_improvement(harness):
    last = max((r.get("ts", 0) for r in read_jsonl(harness.improvements)), default=0)
    return sum(1 for r in read_jsonl(harness.metrics) if r.get("kind") == "build" and r.get("ts", 0) > last)


def run_task(harness, project, task):
    store = TaskStore(project)
    task["status"] = ACTIVE
    store.save(task)
    write_status(harness, project, "working", current={"id": task["id"], "title": task["title"],
                                                      "kind": task["kind"]})
    try:
        record = plan(harness, project, task) if task["kind"] == "plan" else build(harness, project, task)
    except BudgetExceeded:
        task["status"] = PENDING  # not the task's fault; it waits for more budget
        store.save(task)
        raise
    except Exception as exc:  # keep the loop alive; the task goes back to the queue with the error
        log(f"{task['id']} crashed: {exc!r}")
        record = finish(harness, project, task, new_run_dir(harness, f"{task['id']}-crash"), FAILED, None,
                        note=f"orchestrator error: {exc!r}")
    if harness.get("retro", True) and record.get("kind") == "build":
        try:
            retro(harness, project, record)
        except BudgetExceeded:
            pass  # the loop's own check stops before the next task
        except Exception as exc:
            log(f"retro failed: {exc!r}")
    return record


def loop(harness, project, *, once=False, until_empty=False, max_tasks=None):
    from . import improve  # local import: improve depends on engine

    store = TaskStore(project)
    store.recover()
    stop_file = os.path.join(harness.state, "STOP")
    paused = os.path.join(harness.state, "PAUSED")
    if os.path.exists(paused):
        with open(paused) as fh:
            log(f"harness is paused: {fh.read().strip()}")
        return 2
    failures = processed = 0
    while True:
        if os.path.exists(stop_file):
            log("STOP file present; exiting")
            write_status(harness, project, "stopped")
            return 0
        limit = harness.get("budget_usd_total")
        if limit and spent(harness) >= limit:
            log(f"total budget ${limit} spent; exiting")
            write_status(harness, project, "out-of-budget")
            return 3
        for t in intake_inbox(project):
            log(f"intake: {t['id']} {t['title']}")
        for t in store.stuck():
            t["status"] = BLOCKED
            t["history"].append({"ts": time.time(), "event": "blocked by a failed dependency"})
            store.save(t)
        ready = store.ready()
        if not ready:
            write_status(harness, project, "idle")
            if once or until_empty:
                return 0
            time.sleep(harness.get("idle_sleep_seconds", 60))
            continue

        try:
            record = run_task(harness, project, ready[0])
        except BudgetExceeded as exc:
            log(f"{exc}; exiting")
            write_status(harness, project, "out-of-budget")
            return 3
        processed += 1
        failures = 0 if record["outcome"] == DONE else failures + 1
        if failures >= harness.get("max_consecutive_failures", 3):
            reason = f"{failures} consecutive failures; pausing for a human (delete state/PAUSED to clear)"
            with open(os.path.join(harness.state, "PAUSED"), "w") as fh:
                fh.write(reason + "\n")
            log(reason)
            write_status(harness, project, "paused", note=reason)
            return 2

        every = harness.get("improve_every", 0)
        if every and builds_since_improvement(harness) >= every and improve.evals.discover(harness):
            write_status(harness, project, "improving")
            try:
                improve.cycle(harness)
            except BudgetExceeded as exc:
                log(f"{exc}; exiting")
                write_status(harness, project, "out-of-budget")
                return 3
            except Exception as exc:
                log(f"improvement cycle failed: {exc!r}")
        write_status(harness, project, "working")
        if once or (max_tasks and processed >= max_tasks):
            return 0
