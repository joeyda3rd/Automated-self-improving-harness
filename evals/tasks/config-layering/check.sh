set -e
python3 - <<'PY'
import os, tempfile
from confload import load, ConfigError, ConfigSyntaxError, InterpolationCycleError

tmp = tempfile.mkdtemp()
def write(name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p

def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return e
    raise AssertionError(f"expected {exc.__name__} from {a} {kw}")

S = {"app.name": "str", "db.host": "str", "db.port": "int", "db.url": "str", "db.timeout": "duration",
     "ratio": "float", "debug": "bool", "hosts": "list", "labels": "map", "retry.max_conn": "int"}
D = {"app": {"name": "demo"}, "db": {"host": "localhost", "port": "5432",
     "url": "postgres://${db.host}:${db.port}/${app.name}", "timeout": "30s"},
     "ratio": "0.5", "debug": "no", "hosts": "a,b", "labels": {"team": "core", "tier": "dev"},
     "retry": {"max_conn": "4"}}

# --- precedence, merge vs replace, provenance -------------------------------------------
base = write("base.ini", "# comment\n  ; another\n\n[db]\nhost = db1.internal\nport = 6000\n"
             "  timeout =  1h30m  \n[ labels ]\ntier = prod\nregion.zone = eu-1\n")
over = write("over.ini", "ratio = .25e1\nhosts = x\\, y , z\\\\ ,\n[db]\nport = 6001\n")
env = {"APP_DB__PORT": "7000", "APP_RETRY__MAX_CONN": " 12 ", "APP_LABELS__OWNER": "Ops Team",
       "OTHER": "x", "APPX_Y": "1", "APP_DEBUG": "On", "APP_DB____HOST": "ignored", "APP_": "ignored"}
argv = ["--db.host=cli-host", "--labels.tier=staging", "--app.name=a=b", "--app.name=c=d"]
cfg = load(S, D, [base, over], env, "APP", argv)
want = {"app.name": "c=d", "db.host": "cli-host", "db.port": 7000, "db.url": "postgres://cli-host:7000/c=d",
        "db.timeout": 5400, "ratio": 2.5, "debug": True, "hosts": ["x, y", "z\\", ""],
        "labels": {"owner": "Ops Team", "region.zone": "eu-1", "team": "core", "tier": "staging"},
        "retry.max_conn": 12}
assert cfg.as_dict() == want, cfg.as_dict()
assert cfg["db.port"] == 7000 and cfg.get("labels.team") == "core"
prov = {"app.name": "cli", "db.host": "cli", "db.port": "env:APP_DB__PORT", "db.url": "defaults",
        "db.timeout": f"file:{base}", "ratio": f"file:{over}", "debug": "env:APP_DEBUG",
        "hosts": f"file:{over}", "retry.max_conn": "env:APP_RETRY__MAX_CONN", "labels.tier": "cli",
        "labels.team": "defaults", "labels.region.zone": f"file:{base}", "labels.owner": "env:APP_LABELS__OWNER"}
for k, v in prov.items():
    assert cfg.explain(k) == v, (k, cfg.explain(k), v)
for k in ("labels", "labels.nope", "nope"):
    raises(KeyError, cfg.explain, k)
raises(KeyError, cfg.get, "nope")
raises(KeyError, cfg.get, "labels.nope")
# a later file beats an earlier one only for keys it sets; empty map is {}
cfg = load({"a": "list", "b": "int", "m": "map"}, {"a": "1,2,3", "b": "1"},
           [write("f1.ini", "a = 9\nb = 2\n"), write("f2.ini", "a=\n")], {}, "APP", [])
assert cfg.as_dict() == {"a": [], "b": 2, "m": {}}, cfg.as_dict()
os.environ["CFGX_K"] = "from-os"
assert load({"k": "str"}, prefix="CFGX").get("k") == "from-os"   # env defaults to os.environ

# --- all problems at once, exact format ------------------------------------------------
bad = write("bad.ini", "colour = red\ndb = 1\n[db]\nport = 80x\n")
D2 = dict(D, ratio="0.5", debug="no", retry={})
D2["db"] = dict(D["db"], url="${db.hostname}/${db.hostname}/${zz", timeout="30m1h")
D2["app"] = {"name": "${db.url}"}
D2["hosts"] = "${labels}"
e = raises(ConfigError, load, S, D2, [bad], {"APP_RATIO": " 1e", "APP_DB__PASS": "x"}, "APP",
           ["--labels=foo", "--debug=maybe"])
lines = [
    f"colour: unknown key (from file:{bad})",
    f"db: unknown key (from file:{bad})",
    "db.pass: unknown key (from env:APP_DB__PASS)",
    f'db.port: expected int, got "80x" (from file:{bad})',
    'db.timeout: expected duration, got "30m1h" (from defaults)',
    "db.url: unresolved reference ${db.hostname}",
    "db.url: unterminated reference",
    'debug: expected bool, got "maybe" (from cli)',
    "hosts: unresolved reference ${labels}",
    "labels: cannot set a map directly (from cli)",
    'ratio: expected float, got " 1e" (from env:APP_RATIO)',
    "retry.max_conn: missing required value",
]
assert e.problems == lines, e.problems
assert str(e) == "configuration invalid:\n" + "\n".join("- " + l for l in lines), str(e)
assert not isinstance(e, (ConfigSyntaxError, InterpolationCycleError))
# taint propagates through references; a value referencing an unset map entry is unresolved
e = raises(ConfigError, load, {"a": "int", "b": "int", "c": "int", "m": "map"},
           {"a": "${b}", "b": "${c}x", "c": "${m.k}"})
assert e.problems == ["c: unresolved reference ${m.k}"], e.problems

# --- interpolation: across layers, escapes, map entries -----------------------------------
cfg = load({"a": "str", "b": "str", "n": "int", "m": "map", "l": "list"},
           {"a": "pre ${b} $5 $$$$ ${m.x.y}$", "b": "$${n}", "n": "1", "m": {"x": {"y": "<${n}>"}},
            "l": "${m.x.y},${n}"}, (), {"APP_N": "42"}, "APP", [])
assert cfg.get("a") == "pre ${n} $5 $$ <42>$", cfg.get("a")
assert cfg.get("b") == "${n}" and cfg.get("l") == ["<42>", "42"] and cfg.get("m") == {"x.y": "<42>"}
assert cfg.explain("a") == "defaults" and cfg.explain("n") == "env:APP_N"
cfg = load({"base": "str", "port": "int", "url": "str"}, {"base": "80", "port": "${base}1", "url": "h:${port}"},
           (), {"APP_BASE": "90"}, "APP", ["--url=x${port}x"])
assert (cfg.get("port"), cfg.get("url")) == (901, "x901x")

# --- cycles -------------------------------------------------------------------------------
e = raises(InterpolationCycleError, load, {"a": "str", "b": "str", "c": "str", "d": "str", "zz": "int"},
           {"a": "${b}", "b": "${c}", "c": "x${b}", "d": "1", "zz": "bad"}, (), {"APP_UNKNOWN": "1"}, "APP", [])
assert str(e) == "interpolation cycle: b -> c -> b", str(e)
assert isinstance(e, ConfigError)
e = raises(InterpolationCycleError, load, {"a": "str", "d": "str"}, {"a": "${zz}", "d": "${a}${d}"})
assert str(e) == "interpolation cycle: d -> d", str(e)
e = raises(InterpolationCycleError, load, {"p": "str", "q": "str", "m": "map"},
           {"p": "${m.b}", "q": "1", "m": {"a": "${q}", "b": "${m.a}${p}"}})
assert str(e) == "interpolation cycle: m.b -> p -> m.b", str(e)

# --- coercion edge cases ------------------------------------------------------------------
OK = [("int", "+7", 7), ("int", " -0 ", 0), ("float", "1.", 1.0), ("float", ".5", 0.5),
      ("float", "-1E+2", -100.0), ("float", "3", 3.0), ("bool", "YES", True), ("bool", " Off ", False),
      ("bool", "1", True), ("duration", "0", 0), ("duration", "2d", 172800), ("duration", "1d1s", 86401),
      ("duration", "1m30s", 90), ("duration", " 1d2h3m4s ", 93784), ("list", "", []), ("list", "  ", []),
      ("list", "a", ["a"]), ("list", "a,,b", ["a", "", "b"]), ("list", "a\\b", ["a\\b"]),
      ("list", "trail\\", ["trail\\"]), ("list", "\\\\,", ["\\", ""]), ("list", " p , q\\,r ", ["p", "q,r"]),
      ("str", "  keep  ", "  keep  ")]
for typ, raw, val in OK:
    got = load({"k": typ}, argv=["--k=" + raw], env={}).get("k")
    assert got == val and type(got) is type(val), (typ, raw, got, val)
BAD = [("int", "1_000"), ("int", "\u0661\u0662"), ("int", "1.0"), ("int", ""), ("float", "nan"),
       ("float", "inf"), ("float", "1e"), ("float", "."), ("bool", "2"), ("bool", ""), ("bool", "y"),
       ("duration", "1h1h"), ("duration", "30m1h"), ("duration", "5 m"), ("duration", ""),
       ("duration", "+5"), ("duration", "1.5h"), ("duration", "1w")]
for typ, raw in BAD:
    e = raises(ConfigError, load, {"k": typ}, argv=["--k=" + raw], env={})
    assert e.problems == [f'k: expected {typ}, got "{raw}" (from cli)'], (typ, raw, e.problems)

# --- syntax errors ------------------------------------------------------------------------
for text, n in [("a = 1\n\n[]\n", 3), ("[s]\nnovalue\n", 2), ("ok=1\n = v\n", 2), ("[open\n", 1)]:
    p = write("syn.ini", text)
    e = raises(ConfigSyntaxError, load, {"a": "str", "s.ok": "str", "ok": "str"}, {}, [p], {})
    assert str(e) == f"{p}:{n}: syntax error", (text, str(e))
for arg in ["-x=1", "--x", "--=1", "x=1"]:
    e = raises(ConfigSyntaxError, load, {"x": "str"}, {"x": "v"}, (), {}, "APP", [arg])
    assert str(e) == f"bad argument: {arg}", str(e)
assert load({"x": "str"}, {}, (), {}, "APP", ["--x="]).get("x") == ""
raises(ValueError, load, {"x": "integer"}, {"x": "1"}, (), {})
PY
python3 -m unittest -q 2>/dev/null
