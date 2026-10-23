# Make Markdown's extension entry points resolvable without installing the package:
# importlib.metadata reads any *.dist-info on sys.path, and tests run from the repo root.
python3 - <<'PY'
import os, re
pairs = []
for name in ("pyproject.toml", "setup.py"):
    if os.path.exists(name):
        pairs = re.findall(r"""['"]?(\w+)['"]?\s*=\s*['"]?(markdown\.extensions\.\w+:\w+)['"]?""", open(name).read())
        if pairs:
            break
os.makedirs("Markdown-0.dev0.dist-info", exist_ok=True)
with open("Markdown-0.dev0.dist-info/METADATA", "w") as fh:
    fh.write("Metadata-Version: 2.1\nName: Markdown\nVersion: 0.dev0\n")
with open("Markdown-0.dev0.dist-info/entry_points.txt", "w") as fh:
    fh.write("[markdown.extensions]\n" + "".join(f"{k} = {v}\n" for k, v in pairs))
PY

# Test runner: the Markdown suite with Pygments hidden. Pygments may be installed system-wide
# (pytest depends on it), which un-skips CodeHilite tests that only pass with the Pygments
# version this checkout was written against; the suite's own design skips them when absent.
cat > run_tests.py <<'PYEOF'
"""Run the test suite: python3 run_tests.py"""
import sys
import unittest

sys.modules["pygments"] = None  # behave as if Pygments is not installed
suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
PYEOF
