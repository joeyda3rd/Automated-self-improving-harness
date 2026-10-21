#!/usr/bin/env python3
"""Validate benchmark evals: each must FAIL on its seed and PASS on its reference solution.

Usage: python3 tests/validate_evals.py [eval-name ...]

An eval's reference solution lives in evals/tasks/<name>/reference/: files copied over
the seed (same relative paths). Evals without a reference/ are reported as unchecked.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(ROOT, "evals", "tasks")


def run_check(eval_dir, overlay):
    tmp = tempfile.mkdtemp(prefix="ash-validate-")
    ws = os.path.join(tmp, "ws")
    seed = os.path.join(eval_dir, "seed")
    shutil.copytree(seed, ws) if os.path.isdir(seed) else os.makedirs(ws)
    if overlay:
        shutil.copytree(os.path.join(eval_dir, "reference"), ws, dirs_exist_ok=True)
    started = time.time()
    try:
        proc = subprocess.run(["bash", os.path.join(eval_dir, "check.sh")], cwd=ws, capture_output=True,
                              text=True, timeout=300)
        code, out = proc.returncode, (proc.stdout + proc.stderr)[-600:]
    except subprocess.TimeoutExpired:
        code, out = -1, "timed out"
    shutil.rmtree(tmp, ignore_errors=True)
    return code, round(time.time() - started, 1), out


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
