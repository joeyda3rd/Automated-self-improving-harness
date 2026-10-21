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
