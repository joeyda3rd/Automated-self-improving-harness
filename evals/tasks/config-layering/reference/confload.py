"""Layered configuration loader: defaults < files < env < cli, schema-typed."""
import os
import re

TYPES = {"str", "int", "float", "bool", "list", "duration", "map"}


class ConfigError(Exception):
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = list(problems or [])


class ConfigSyntaxError(ConfigError):
    pass


class InterpolationCycleError(ConfigError):
    pass


def _flatten(d, prefix=""):
    out = []
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_flatten(v, key))
        else:
            if not isinstance(v, str):
                raise TypeError(f"default {key} must be a string")
            out.append((key, v))
    return out


def _parse_file(path):
    items = {}
    section = ""
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh.read().split("\n"), 1):
            line = raw.strip()
            if not line or line[0] in "#;":
                continue
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1].strip()
                if not name:
                    raise ConfigSyntaxError(f"{path}:{n}: syntax error")
                section = name
                continue
            if "=" not in line:
                raise ConfigSyntaxError(f"{path}:{n}: syntax error")
            k, v = line.split("=", 1)
            k = k.strip()
            if not k:
                raise ConfigSyntaxError(f"{path}:{n}: syntax error")
            items[f"{section}.{k}" if section else k] = v.strip()
    return list(items.items())


def _env_layers(env, prefix):
    out = []
    head = prefix + "_"
    for name in sorted(env):
        if not name.startswith(head):
            continue
        parts = name[len(head):].split("__")
        if not all(parts):
            continue
        out.append((f"env:{name}", [(".".join(p.lower() for p in parts), env[name])]))
    return out


def _cli_layer(argv):
    items = {}
    for arg in argv:
        if not arg.startswith("--") or "=" not in arg or arg.index("=") == 2:
            raise ConfigSyntaxError(f"bad argument: {arg}")
        k, v = arg[2:].split("=", 1)
        items[k] = v
    return list(items.items())


_INT = re.compile(r"[+-]?[0-9]+")
_FLOAT = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")
_DUR = re.compile(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")
_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}


def _split_list(s):
    if not s.strip():
        return []
    items, cur, i = [], "", 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in ",\\":
            cur += s[i + 1]
            i += 2
            continue
        if c == ",":
            items.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    items.append(cur)
    return [x.strip() for x in items]


def _coerce(typ, s):
    """Return (ok, value)."""
    if typ == "str":
        return True, s
    if typ == "list":
        return True, _split_list(s)
    t = s.strip()
    if typ == "int":
        return (True, int(t)) if _INT.fullmatch(t) else (False, None)
    if typ == "float":
        return (True, float(t)) if _FLOAT.fullmatch(t) else (False, None)
    if typ == "bool":
        if t.lower() in _TRUE:
            return True, True
        if t.lower() in _FALSE:
            return True, False
        return False, None
    if typ == "duration":
        if _INT.fullmatch(t) and t[0] not in "+-":
            return True, int(t)
        m = _DUR.fullmatch(t)
        if not t or not m:
            return False, None
        d, h, mi, se = (int(x) if x else 0 for x in m.groups())
        return True, ((d * 24 + h) * 60 + mi) * 60 + se
    raise AssertionError(typ)


class Config:
    def __init__(self, schema, values, prov):
        self._schema = schema
        self._values = values
        self._prov = prov

    def get(self, key):
        if key in self._schema:
            if self._schema[key] == "map":
                pre = key + "."
                return {k[len(pre):]: v for k, v in sorted(self._values.items()) if k.startswith(pre)}
            return self._values[key]
        if key in self._values:
            return self._values[key]
        raise KeyError(key)

    __getitem__ = get

    def explain(self, key):
        if key in self._prov:
            return self._prov[key]
        raise KeyError(key)

    def as_dict(self):
        return {k: self.get(k) for k in sorted(self._schema)}


def load(schema, defaults=None, files=(), env=None, prefix="APP", argv=()):
    for k, t in schema.items():
        if t not in TYPES:
            raise ValueError(f"bad type for {k}: {t}")
    maps = [k for k, t in schema.items() if t == "map"]

    layers = [("defaults", _flatten(defaults or {}))]
    for path in files:
        layers.append((f"file:{path}", _parse_file(path)))
    layers.extend(_env_layers(os.environ if env is None else env, prefix))
    layers.append(("cli", _cli_layer(argv)))

    problems = []
    raw, prov = {}, {}
    for label, items in layers:
        for key, value in items:
            if key in schema and schema[key] == "map":
                problems.append((key, f"cannot set a map directly (from {label})"))
            elif key in schema or any(key.startswith(m + ".") and len(key) > len(m) + 1 for m in maps):
                raw[key], prov[key] = value, label
            else:
                problems.append((key, f"unknown key (from {label})"))

    resolved, tainted = {}, set()

    def resolve(key, path):
        if key in resolved:
            return
        if key in path:
            cyc = path[path.index(key):] + [key]
            raise InterpolationCycleError("interpolation cycle: " + " -> ".join(cyc))
        path = path + [key]
        s, out, i, bad = raw[key], "", 0, False
        seen = set()
        while i < len(s):
            if s.startswith("$$", i):
                out += "$"
                i += 2
            elif s.startswith("${", i):
                j = s.find("}", i + 2)
                if j < 0:
                    problems.append((key, "unterminated reference"))
                    bad = True
                    out += s[i:]
                    break
                name = s[i + 2:j]
                if name in raw:
                    resolve(name, path)
                    if name in tainted:
                        bad = True
                    out += resolved[name]
                else:
                    if name not in seen:
                        problems.append((key, f"unresolved reference ${{{name}}}"))
                        seen.add(name)
                    bad = True
                    out += s[i:j + 1]
                i = j + 1
            else:
                out += s[i]
                i += 1
        resolved[key] = out
        if bad:
            tainted.add(key)

    for key in sorted(raw):
        resolve(key, [])

    values = {}
    for key, typ in schema.items():
        if typ == "map":
            continue
        if key not in raw:
            problems.append((key, "missing required value"))
            continue
        if key in tainted:
            continue
        ok, val = _coerce(typ, resolved[key])
        if ok:
            values[key] = val
        else:
            problems.append((key, f'expected {typ}, got "{resolved[key]}" (from {prov[key]})'))
    for key in raw:
        if key not in schema and key not in tainted:
            values[key] = resolved[key]

    if problems:
        lines = [f"{k}: {m}" for k, m in sorted(set(problems))]
        raise ConfigError("configuration invalid:\n" + "\n".join("- " + l for l in lines), lines)
    return Config(schema, values, prov)
