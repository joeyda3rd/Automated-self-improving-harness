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
    improve.cycle(h)


def cmd_eval(h, args):
    if args.repeats:
        h.cfg["eval_repeats"] = args.repeats
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

    for name, fn, text in [("status", cmd_status, "show the queue"),
                           ("report", cmd_report, "success and cost per harness version"),
                           ("improve", cmd_improve, "run one self-improvement cycle now"),
                           ("lessons", cmd_lessons, "show what the harness has learned"),
                           ("pause", cmd_pause, "stop the loop after the current task"),
                           ("resume", cmd_resume, "clear a pause or circuit-breaker trip")]:
        sub.add_parser(name, help=text).set_defaults(fn=fn)

    s = sub.add_parser("eval", help="benchmark the harness (or a candidate plugin dir)")
    s.add_argument("--plugin-dir")
    s.add_argument("--label", default="manual")
    s.add_argument("--only", action="append", help="eval name to run (repeatable; default: all)")
    s.add_argument("--repeats", type=int, help="runs per eval (default: eval_repeats in harness.json)")
    s.set_defaults(fn=cmd_eval)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    h = Harness.load()
    os.makedirs(h.state, exist_ok=True)
    return args.fn(h, args) or 0


if __name__ == "__main__":
    sys.exit(main())
