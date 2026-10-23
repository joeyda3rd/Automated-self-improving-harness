# Test runner for this checkout: the whole unittest suite except one slow concurrency
# stress test (~70 s) that is unrelated to any task here.
cat > run_tests.py <<'PY'
"""Run the test suite: python3 run_tests.py (skips the slow TestConcurrentTee stress test)."""
import sys
import unittest

SLOW = ("TestConcurrentTee",)


def keep(suite):
    out = unittest.TestSuite()
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            out.addTests(keep(t))
        elif not any(s in t.id() for s in SLOW):
            out.addTest(t)
    return out


suite = keep(unittest.defaultTestLoader.discover("tests", top_level_dir="."))
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
PY
