#!/usr/bin/env python3
"""Turn a real bug-fix commit from a public repository into an ASH eval skeleton.

Usage:
  python3 tests/make_git_eval.py NAME --clone LOCAL_CLONE --url URL --commit SHA \\
      --paths markdown tests pyproject.toml --src-prefix markdown/ --test-prefix tests/ \\
      --test-cmd "python3 -m unittest discover -s tests -q" [--prepare FILE]

Writes evals/tasks/NAME/ with:
  seed.git.json  the fix commit's PARENT, exported at eval time (no copy in this repo)
  prepare.sh     optional workspace preparation (copied from --prepare)
  hidden/        the test files the fix commit changed: the hidden acceptance tests
  reference/     the source files the fix commit changed: the reference solution
  check.sh       lays hidden/ over the workspace and runs the full test command
  task.json      a stub: write the bug report (symptom, not fix) by hand before use
"""
import argparse
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(clone, *args):
    return subprocess.run(["git", "-C", clone, *args], capture_output=True, check=True).stdout


def write_rev_files(clone, rev, files, dest):
    for f in files:
        try:
            blob = git(clone, "show", f"{rev}:{f}")
        except subprocess.CalledProcessError:
            continue  # deleted by the fix
        path = os.path.join(dest, f)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--clone", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--paths", nargs="+", required=True)
    ap.add_argument("--src-prefix", required=True)
    ap.add_argument("--test-prefix", required=True)
    ap.add_argument("--test-cmd", required=True)
    ap.add_argument("--prepare")
    a = ap.parse_args()

    sha = git(a.clone, "rev-parse", a.commit).decode().strip()
    parent = git(a.clone, "rev-parse", f"{sha}^").decode().strip()
    changed = git(a.clone, "diff", "--name-only", parent, sha).decode().split()
    tests = [f for f in changed if f.startswith(a.test_prefix)]
    src = [f for f in changed if f.startswith(a.src_prefix)]
    paths = [p for p in a.paths
             if subprocess.run(["git", "-C", a.clone, "cat-file", "-e", f"{parent}:{p}"]).returncode == 0]

    out = os.path.join(ROOT, "evals", "tasks", a.name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "seed.git.json"), "w") as fh:
        json.dump({"url": a.url, "rev": parent, "paths": paths, "fix": sha}, fh, indent=2)
        fh.write("\n")
    write_rev_files(a.clone, sha, tests, os.path.join(out, "hidden"))
    write_rev_files(a.clone, sha, src, os.path.join(out, "reference"))
    if a.prepare:
        with open(a.prepare) as src_fh, open(os.path.join(out, "prepare.sh"), "w") as fh:
            fh.write(src_fh.read())
    with open(os.path.join(out, "check.sh"), "w") as fh:
        fh.write("set -e\n# the fix commit's own tests (hidden) over the builder's work, then the whole suite\n"
                 'cp -r "$ASH_EVAL_DIR/hidden/." .\n'
                 f"{a.test_cmd} 2>&1 | tail -20\nexit ${{PIPESTATUS[0]}}\n")
    stub = os.path.join(out, "task.json")
    if not os.path.exists(stub):
        with open(stub, "w") as fh:
            json.dump({"title": "TODO", "spec": "TODO: a bug report (symptom and one example, never the fix)",
                       "acceptance": [], "verify_cmd": a.test_cmd,
                       "source": f"{a.url}/commit/{sha}"}, fh, indent=2)
            fh.write("\n")
    print(f"{out}: {len(tests)} hidden test files, {len(src)} reference files")


if __name__ == "__main__":
    main()
