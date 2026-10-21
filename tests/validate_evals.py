#!/usr/bin/env python3
"""Validate benchmark evals: each must FAIL on its seed and PASS on its reference solution.

Usage: python3 tests/validate_evals.py [eval-name ...]

An eval's reference solution lives in evals/tasks/<name>/reference/: files copied over
the seed (same relative paths). Evals without a reference/ are reported as unchecked.
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(ROOT, "evals", "tasks")
sys.path.insert(0, ROOT)

from ash import evals  # noqa: E402


def run_check(eval_dir, overlay):
    tmp = tempfile.mkdtemp(prefix="ash-validate-")
    ws = os.path.join(tmp, "ws")
    evals.lay_seed(os.path.join(ROOT, "state"), eval_dir, ws)
    if overlay:
        shutil.copytree(os.path.join(eval_dir, "reference"), ws, dirs_exist_ok=True)
    started = time.time()
    passed, out = evals.run_check(eval_dir, ws, timeout=300)
    shutil.rmtree(tmp, ignore_errors=True)
    return (0 if passed else 1), round(time.time() - started, 1), out


def main(names):
    bad = 0
    for name in names or sorted(os.listdir(TASKS)):
        d = os.path.join(TASKS, name)
        if not os.path.exists(os.path.join(d, "check.sh")):
            continue
        seed_code, _, _ = run_check(d, overlay=False)
        if not os.path.isdir(os.path.join(d, "reference")):
            print(f"?    {name}: seed {'fails' if seed_code else 'PASSES'}; no reference/ to check")
            bad += seed_code == 0
            continue
        ref_code, secs, out = run_check(d, overlay=True)
        ok = seed_code != 0 and ref_code == 0
        bad += not ok
        print(f"{'ok  ' if ok else 'BAD '} {name}: seed {'fails' if seed_code else 'PASSES'}, "
              f"reference {'passes' if ref_code == 0 else 'FAILS'} ({secs}s)")
        if ref_code != 0:
            print("     " + out.replace("\n", "\n     "))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
