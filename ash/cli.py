"""ash: command-line interface to the Automated Self-improving Harness."""
import argparse
import json
import os
import sys
from collections import defaultdict

from . import engine, evals, improve
from .config import Harness, Project, read_jsonl
from .memory import read_lessons
from .tasks import TaskStore


def _project(args):
    return Project(os.path.abspath(args.project))


def cmd_init(h, args):
    p = _project(args)
    engine.init_project(p, verify_cmd=args.verify, base_branch=args.base)
    print(f"initialised {p.root} (base branch {p.base_branch}, verify: {p.verify_cmd or 'none yet'})")


def cmd_assign(h, args):
    """Hand the harness an assignment; the planner turns it into tasks."""
    text = args.text
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as fh:
            text = fh.read()
    title = text.strip().splitlines()[0].lstrip("# ").strip()[:120]
    t = TaskStore(_project(args)).add(title, text, kind="plan", priority=2, source="assign")
    print(f"{t['id']} (plan) {t['title']}")


def cmd_add(h, args):
    t = TaskStore(_project(args)).add(args.title, args.spec or "", acceptance=args.accept,
                                      depends_on=args.after, priority=args.priority)
    print(f"{t['id']} (build) {t['title']}")


def cmd_run(h, args):
    if args.no_improve:
        h.cfg["improve_every"] = 0
    return engine.loop(h, _project(args), once=args.once, until_empty=args.until_empty,
                       max_tasks=args.max_tasks)


def cmd_status(h, args):
    p = _project(args)
    store = TaskStore(p)
    print(f"project {p.root}  verify: {p.verify_cmd or '-'}  counts: {store.counts()}")
    for t in store.all():
        deps = f" after {','.join(t['depends_on'])}" if t.get("depends_on") else ""
        print(f"  {t['id']} [{t['status']:<7}] p{t.get('priority', 3)} {t['kind']:<5} {t['title'][:70]}{deps}")
    for flag in ("PAUSED", "STOP"):
        path = os.path.join(h.state, flag)
        if os.path.exists(path):
            with open(path) as fh:
                print(f"harness {flag}: {fh.read().strip()}")
    from . import daemon
    d = daemon.status(h)
    if d["alive"]:
        print(f"daemon: running (pid {d.get('pid')}, {d.get('phase')}, heartbeat {d.get('heartbeat_age_s', '?')}s ago, "
              f"last: {d.get('last')})")
    else:
        print(f"daemon: not running (auto-start {'on' if d['enabled'] else 'off'}; last seen {d.get('phase', 'never')})")


def cmd_report(h, args):
    """How the harness is doing, per harness version: the self-improvement learning curve."""
    by = defaultdict(list)
    for r in read_jsonl(h.metrics):
        if r.get("kind") == "build":
            by[r.get("harness_commit") or "-"].append(r)
    print(f"{'harness':<14}{'runs':>6}{'done':>7}{'cost/run':>10}{'turns':>8}{'gate':>6}")
    for commit, rows in by.items():
        n = len(rows)
        print(f"{commit:<14}{n:>6}{sum(r['outcome'] == 'done' for r in rows) / n:>7.0%}"
              f"{sum(r['cost_usd'] for r in rows) / n:>10.3f}{sum(r['turns'] for r in rows) / n:>8.1f}"
              f"{sum(r.get('gate_failures', 0) for r in rows) / n:>6.1f}")
    limit = h.get("budget_usd_total")
    print(f"total spend ${engine.spent(h):.2f}" + (f" of ${limit:.2f} budget" if limit else " (no total budget set)"))
    for i in read_jsonl(h.improvements)[-10:]:
        print(f"  {'+' if i.get('accepted') else '-'} {i.get('hypothesis', '')[:70]}  [{i.get('reason')}]")


def cmd_improve(h, args):
    if args.list:
        for f in sorted(os.listdir(improve.archive_dir(h))) if os.path.isdir(improve.archive_dir(h)) else []:
            if f.endswith(".json"):
                meta = json.load(open(os.path.join(improve.archive_dir(h), f)))
                print(f"{f[:-5]}  {meta.get('change_summary', '')[:70]}  [{meta.get('reason')}]")
        return 0
    improve.cycle(h, retry=args.retry)


def cmd_daemon(h, args):
    from . import daemon
    root = os.path.abspath(args.project)
    project_root = root if os.path.exists(os.path.join(root, ".ash", "project.json")) else None
    if args.action == "enable":
        with open(daemon.paths(h)[2], "w") as fh:
            fh.write(project_root or "")
        print(f"auto-start enabled{' for ' + project_root if project_root else ''}: "
              "the SessionStart hook keeps a daemon running")
    elif args.action == "disable":
        if os.path.exists(daemon.paths(h)[2]):
            os.remove(daemon.paths(h)[2])
        print("auto-start disabled")
    elif args.action == "stop":
        print(daemon.request_stop(h))
    elif args.action == "status":
        print(json.dumps(daemon.status(h), indent=2))
    elif args.ensure:
        enabled = daemon.paths(h)[2]
        if args.if_enabled and not os.path.exists(enabled):
            return 0
        if not project_root and os.path.exists(enabled):
            with open(enabled) as fh:
                project_root = fh.read().strip() or None  # the project recorded by `daemon enable`
        print(daemon.ensure(h, project_root))
    else:
        return daemon.Daemon(h, Project(project_root) if project_root else None,
                             max_iterations=args.max_iterations).run()


def cmd_curate(h, args):
    from . import curate
    names = [args.source] if args.source else list(curate.sources(h))
    if args.stage == "mine":
        for n in names:
            print(f"{n}: {curate.mine(h, n, limit=args.limit)} new candidates")
    elif args.stage == "make":
        for n in names:
            print(f"{n}: made {curate.make(h, n, limit=args.limit)}")
    elif args.stage == "report":
        print(curate.report(h, limit=args.limit))
    elif args.stage == "screen":
        s = curate.screen(h)
        print("nothing to screen" if s is None else {k: v["rate"] for k, v in s["per_task"].items()})
    elif args.stage == "audit":
        print(curate.audit(h, limit=args.limit))
    elif args.stage == "gate":
        print(json.dumps(curate.regate(h), indent=2))
    else:
        print(json.dumps(curate.grow(h, per_source=args.limit), indent=2))


def cmd_doctor(h, args):
    """Pre-flight checks before running unattended. Exit 1 if anything would stop the harness."""
    import shutil as _sh
    import subprocess as _sp
    from . import claude as _claude, daemon as _daemon, evals as _evals
    problems, notes = [], []

    def check(ok, good, bad, fatal=True):
        (notes if ok else (problems if fatal else notes)).append(("ok   " if ok else ("FAIL " if fatal else "warn ")) + (good if ok else bad))

    binary = _sh.which(h.claude_bin)
    version = _sp.run([h.claude_bin, "--version"], capture_output=True, text=True).stdout.strip() if binary else ""
    check(bool(version), f"claude CLI: {version}", f"claude CLI not found: {h.claude_bin}")
    check(bool(_sh.which("git")), "git present", "git not found")
    check(sys.version_info >= (3, 9), f"python {sys.version.split()[0]}", "python >= 3.9 required")
    check(os.path.exists(os.path.join(h.plugin_dir, "hooks", "hooks.json")), "plugin hooks present", "plugin/hooks/hooks.json missing")
    roles = [r for r in ("builder", "planner", "retro", "improver") if not os.path.exists(os.path.join(h.plugin_dir, "roles", f"{r}.md"))]
    check(not roles, "role prompts present", f"missing role prompts: {roles}")
    try:
        probe = os.path.join(h.state, ".doctor"); open(probe, "w").close(); os.remove(probe)
        check(True, "state/ writable", "")
    except OSError as exc:
        check(False, "", f"state/ not writable: {exc}")
    left = _claude.remaining(h)
    check(left is None or left > 0.5, f"budget: ${left:.2f} left of ${h.get('budget_usd_total')}" if left is not None
          else "budget: no total limit set (warn: unbounded spend)", "budget exhausted")
    notes.append(f"info self-improvement share of spend so far: {_claude.meta_share(h):.0%} "
                 f"(cap while building: {h.get('meta_budget_share', 0.4):.0%})")
    gate, smoke = _evals.gate_set(h), _evals.smoke_set(h)
    check(len(gate - smoke) >= 1, f"gate: {len(gate - smoke)} discriminating + {len(smoke)} smoke "
          f"(daemon curates below {h.get('min_gate_discriminating', 8)})", "gate is empty: improvement has no signal", fatal=False)
    check(_sh.which("pytest") is not None or _sp.run([sys.executable, "-c", "import pytest"]).returncode == 0,
          "pytest importable (needed by pytest-based evals)", "pytest missing: pytest-based evals cannot run", fatal=False)
    mutable, kernel = h.get("mutable_paths", []), ("ash/", "plugin/hooks/", "evals/", "harness.json", "bin/", "tests/")
    check(not [m for m in mutable if any(m.startswith(k) for k in kernel)], "mutable paths exclude the kernel",
          f"mutable_paths overlap the kernel: {mutable}")
    d = _daemon.status(h)
    notes.append(f"info daemon: {'running, ' + str(d.get('phase')) if d['alive'] else 'not running'}; "
                 f"auto-start {'on' if d['enabled'] else 'off'}")
    print("\n".join(notes + problems))
    return 1 if problems else 0


def cmd_eval(h, args):
    if args.repeats:
        h.cfg["eval_repeats"] = args.repeats
    if args.effort:
        h.cfg["effort"] = dict(h.get("effort") or {}, builder=args.effort)
    summary = evals.run_suite(h, os.path.abspath(args.plugin_dir or h.plugin_dir), args.label,
                              names=set(args.only) if args.only else None)
    if summary.get("incomplete"):
        print(f"stopped early: total budget ${h.get('budget_usd_total')} reached (spent ${engine.spent(h):.2f})")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    for r in summary["results"]:
        print(f"  {'PASS' if r['passed'] else 'FAIL'} {r['eval']} ${r['cost_usd']:.3f} {r['turns']} turns")


def cmd_lessons(h, args):
    print("\n".join(read_lessons(h.learnings)) or "no lessons yet")


def cmd_pause(h, args):
    with open(os.path.join(h.state, "STOP"), "w") as fh:
        fh.write("stopped by user\n")
    print("the loop will stop after the current task")


def cmd_resume(h, args):
    for flag in ("PAUSED", "STOP"):
        path = os.path.join(h.state, flag)
        if os.path.exists(path):
            os.remove(path)
    print("cleared; start the loop again with `ash run`")


def parser():
    ap = argparse.ArgumentParser(prog="ash", description=__doc__)
    ap.add_argument("-C", "--project", default=os.getcwd(), help="project directory (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="prepare a project directory for the harness")
    s.add_argument("--verify", help="command that must pass for work to count as done, e.g. 'npm test'")
    s.add_argument("--base", help="branch the harness integrates into (default: current)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("assign", help="give the harness an assignment to plan and build ('@file.md' reads a file)")
    s.add_argument("text")
    s.set_defaults(fn=cmd_assign)

    s = sub.add_parser("add", help="queue a single build task")
    s.add_argument("title")
    s.add_argument("--spec")
    s.add_argument("--accept", action="append", help="acceptance criterion (repeatable)")
    s.add_argument("--after", action="append", help="task id this depends on (repeatable)")
    s.add_argument("--priority", type=int, default=3)
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("run", help="work the queue continuously (Ctrl-C or `ash pause` to stop)")
    s.add_argument("--once", action="store_true", help="work one task and exit")
    s.add_argument("--until-empty", action="store_true", help="exit when nothing is ready")
    s.add_argument("--max-tasks", type=int)
    s.add_argument("--no-improve", action="store_true", help="build only; never start a self-improvement cycle")
    s.set_defaults(fn=cmd_run)

    for name, fn, text in [("doctor", cmd_doctor, "pre-flight checks before running unattended"),
                           ("status", cmd_status, "show the queue"),
                           ("report", cmd_report, "success and cost per harness version"),
                           ("lessons", cmd_lessons, "show what the harness has learned"),
                           ("pause", cmd_pause, "stop the loop after the current task"),
                           ("resume", cmd_resume, "clear a pause or circuit-breaker trip")]:
        sub.add_parser(name, help=text).set_defaults(fn=fn)

    s = sub.add_parser("curate", help="grow the benchmark from real bug fixes (mine/make/report/screen/audit/gate)")
    s.add_argument("stage", nargs="?", default="grow",
                   choices=["mine", "make", "report", "screen", "audit", "gate", "grow"])
    s.add_argument("--source", help="one entry of evals/sources.json (default: all)")
    s.add_argument("--limit", type=int, default=3)
    s.set_defaults(fn=cmd_curate)

    s = sub.add_parser("daemon", help="the supervisor: build queued work and self-improve, single instance")
    s.add_argument("action", nargs="?", choices=["enable", "disable", "stop", "status"])
    s.add_argument("--ensure", action="store_true", help="start in the background unless already running")
    s.add_argument("--if-enabled", action="store_true", help="with --ensure: only if auto-start is enabled")
    s.add_argument("--max-iterations", type=int)
    s.set_defaults(fn=cmd_daemon)

    s = sub.add_parser("improve", help="run one self-improvement cycle now")
    s.add_argument("--retry", metavar="ID", help="re-benchmark an archived candidate instead of proposing a new one")
    s.add_argument("--list", action="store_true", help="list archived candidates")
    s.set_defaults(fn=cmd_improve)

    s = sub.add_parser("eval", help="benchmark the harness (or a candidate plugin dir)")
    s.add_argument("--plugin-dir")
    s.add_argument("--label", default="manual")
    s.add_argument("--only", action="append", help="eval name to run (repeatable; default: all)")
    s.add_argument("--repeats", type=int, help="runs per eval (default: eval_repeats in harness.json)")
    s.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="builder effort for this run")
    s.set_defaults(fn=cmd_eval)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    h = Harness.load()
    os.makedirs(h.state, exist_ok=True)
    return args.fn(h, args) or 0


if __name__ == "__main__":
    sys.exit(main())
