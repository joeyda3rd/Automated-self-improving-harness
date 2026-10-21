#!/usr/bin/env python3
"""Stand-in for `claude -p` used by the tests. Behaviour is chosen by ASH_ROLE and FAKE_* env vars."""
import json
import os
import sys
import uuid

argv = sys.argv[1:]


def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None


if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a") as fh:
        fh.write(json.dumps({"role": os.environ.get("ASH_ROLE"), "cwd": os.getcwd(), "argv": argv}) + "\n")

role = os.environ.get("ASH_ROLE")
if os.environ.get("FAKE_SLEEP"):
    __import__("time").sleep(float(os.environ["FAKE_SLEEP"]))
resumed = arg("--resume") is not None
out = {}
if role == "planner":
    out = {"tasks": [{"title": "Add feature A", "spec": "a", "acceptance": ["A exists"]},
                     {"title": "Add feature B", "spec": "b", "depends_on": [0]}],
           "verify_cmd": "ls feature_*.txt"}
elif role == "builder":
    if os.environ.get("FAKE_LAZY_FIRST") and not resumed:
        out = {"status": "done", "summary": "claimed done without doing it"}
    else:
        n = len([f for f in os.listdir(".") if f.startswith("feature_")])
        with open(f"feature_{n}_{uuid.uuid4().hex[:6]}.txt", "w") as fh:
            fh.write("built\n")
        out = {"status": "done", "summary": "added a feature file",
               "follow_ups": [{"title": "Polish", "spec": "p"}] if os.environ.get("FAKE_FOLLOWUP") else []}
elif role == "eval":
    skill = os.path.join(arg("--plugin-dir"), "skills", "build-task", "SKILL.md")
    if "IMPROVED" in open(skill).read():
        open("done.txt", "w").write("ok\n")
    out = {"status": "done", "summary": "eval"}
elif role == "retro":
    out = {"lessons": [{"text": "Run focused tests while iterating.", "scope": "harness"},
                       {"text": "Feature files live at the repo root.", "scope": "project"}],
           "lesson_feedback": [{"id": i, "verdict": os.environ.get("FAKE_VERDICT", "helpful")}
                               for i in __import__("re").findall(r"L-[0-9a-f]{6}", argv[argv.index("-p") + 1])],
           "harness_suggestion": "builders should batch reads"}
elif role == "improver":
    with open("plugin/skills/build-task/SKILL.md", "a") as fh:
        fh.write("\nIMPROVED: batch your reads.\n")
    if os.environ.get("FAKE_TOUCH_KERNEL"):
        with open("ash/evil.py", "w") as fh:
            fh.write("# loosen the rules\n")
    out = {"hypothesis": "batching reads saves turns", "change_summary": "add a read-batching step",
           "expected_effect": "fewer turns"}

print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": json.dumps(out),
                  "session_id": arg("--resume") or arg("--session-id") or str(uuid.uuid4()),
                  "total_cost_usd": 0.01, "num_turns": 3, "structured_output": out}))
