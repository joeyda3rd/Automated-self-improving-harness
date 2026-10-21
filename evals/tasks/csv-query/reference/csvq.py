"""A tiny SQL-like query engine over CSV files."""
import csv
import io
import re
from decimal import Decimal, ROUND_HALF_UP


class QueryError(Exception):
    pass


KEYWORDS = {"SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "ASC", "DESC", "LIMIT",
            "AND", "OR", "NOT", "IS", "NULL"}
AGGS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
NUM_RE = re.compile(r"-?[0-9]+(\.[0-9]+)?\Z")
TOKEN_RE = re.compile(r"""\s*(?:
    (?P<num>-?[0-9]+(?:\.[0-9]+)?(?![A-Za-z0-9_]))
  | (?P<str>'(?:[^']|'')*')
  | (?P<op><>|!=|<=|>=|=|<|>|\(|\)|,|\*)
  | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<path>[A-Za-z0-9_./-]+)
)""", re.X)

# truth values: True, False, None (unknown)
# cell values: None (NULL) or a (sort value, original text) tuple; aggregate results: Agg


class Agg:
    def __init__(self, value):
        self.value = value


def tokenize(sql):
    toks, pos = [], 0
    sql = sql.rstrip()
    while pos < len(sql):
        m = TOKEN_RE.match(sql, pos)
        if not m or m.end() == pos:
            raise QueryError(f"unexpected text at {pos}: {sql[pos:pos + 10]!r}")
        kind = m.lastgroup
        text = m.group(kind)
        toks.append((kind, text, m.start(kind), m.end()))
        pos = m.end()
    return toks, sql


class Parser:
    def __init__(self, sql):
        self.toks, self.sql = tokenize(sql)
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None, len(self.sql), len(self.sql))

    def kw(self, word):
        kind, text = self.peek()[:2]
        if kind == "word" and text.upper() == word:
            self.i += 1
            return True
        return False

    def expect_kw(self, word):
        if not self.kw(word):
            raise QueryError(f"expected {word}")

    def op(self, sym):
        kind, text = self.peek()[:2]
        if kind == "op" and text == sym:
            self.i += 1
            return True
        return False

    def expect_op(self, sym):
        if not self.op(sym):
            raise QueryError(f"expected {sym!r}")

    def ident(self):
        kind, text = self.peek()[:2]
        if kind != "word" or text.upper() in KEYWORDS:
            raise QueryError(f"expected column name, got {text!r}")
        self.i += 1
        return text

    def item(self, allow_plain=True):
        kind, text = self.peek()[:2]
        nxt = self.peek(1)
        if kind == "word" and text.upper() in AGGS and nxt[0] == "op" and nxt[1] == "(":
            self.i += 2
            fn = text.upper()
            if fn == "COUNT" and self.op("*"):
                arg = "*"
            else:
                arg = self.ident()
            self.expect_op(")")
            return ("agg", fn, arg)
        return ("col", self.ident())

    def parse(self):
        q = {}
        self.expect_kw("SELECT")
        if self.op("*"):
            q["select"] = "*"
        else:
            items = [self.item()]
            while self.op(","):
                items.append(self.item())
            q["select"] = items
        self.expect_kw("FROM")
        kind, text, start, _ = self.peek()
        if kind is None:
            raise QueryError("expected path")
        # a path may have been split into several adjacent tokens (e.g. "t.csv" -> word + path)
        end = start
        while self.i < len(self.toks) and self.toks[self.i][0] in ("word", "path", "num") \
                and self.toks[self.i][2] == end:
            end = self.toks[self.i][3]
            self.i += 1
        path = self.sql[start:end]
        if not path or not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
            raise QueryError("bad path")
        q["path"] = path
        q["where"] = self.expr() if self.kw("WHERE") else None
        q["group"] = []
        if self.kw("GROUP"):
            self.expect_kw("BY")
            q["group"].append(self.ident())
            while self.op(","):
                q["group"].append(self.ident())
        q["order"] = []
        if self.kw("ORDER"):
            self.expect_kw("BY")
            while True:
                key = self.item()
                desc = False
                if self.kw("DESC"):
                    desc = True
                else:
                    self.kw("ASC")
                q["order"].append((key, desc))
                if not self.op(","):
                    break
        q["limit"] = None
        if self.kw("LIMIT"):
            kind, text = self.peek()[:2]
            if kind != "num" or not text.isdigit():
                raise QueryError("LIMIT needs a non-negative integer")
            self.i += 1
            q["limit"] = int(text)
        if self.i != len(self.toks):
            raise QueryError(f"unexpected {self.peek()[1]!r}")
        return q

    def expr(self):
        node = self.and_expr()
        while self.kw("OR"):
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.kw("AND"):
            node = ("and", node, self.not_expr())
        return node

    def not_expr(self):
        if self.kw("NOT"):
            return ("not", self.not_expr())
        return self.predicate()

    def predicate(self):
        if self.op("("):
            node = self.expr()
            self.expect_op(")")
            return node
        left = self.operand()
        if self.kw("IS"):
            neg = self.kw("NOT")
            self.expect_kw("NULL")
            return ("isnull", left, neg)
        kind, text = self.peek()[:2]
        if kind == "op" and text in ("=", "!=", "<>", "<", "<=", ">", ">="):
            self.i += 1
            return ("cmp", "!=" if text == "<>" else text, left, self.operand())
        raise QueryError("expected comparison")

    def operand(self):
        kind, text = self.peek()[:2]
        if kind == "num":
            self.i += 1
            return ("lit", "num", Decimal(text))
        if kind == "str":
            self.i += 1
            return ("lit", "str", text[1:-1].replace("''", "'"))
        return ("col", self.ident())


def load(path):
    try:
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
    except OSError as e:
        raise QueryError(f"cannot read {path}: {e}")
    if not rows:
        raise QueryError("empty file")
    header, data = rows[0], rows[1:]
    types = {}
    for j, name in enumerate(header):
        vals = [r[j] if j < len(r) else "" for r in data]
        types[name] = "num" if all(v == "" or NUM_RE.match(v) for v in vals) else "str"
    recs = []
    for r in data:
        rec = {}
        for j, name in enumerate(header):
            v = r[j] if j < len(r) else ""
            rec[name] = None if v == "" else ((Decimal(v), v) if types[name] == "num" else (v, v))
        recs.append(rec)
    return header, types, recs


def run(sql):
    if not isinstance(sql, str):
        raise QueryError("query must be a string")
    q = Parser(sql).parse()
    header, types, recs = load(q["path"])

    def check_col(c):
        if c not in types:
            raise QueryError(f"unknown column {c!r}")

    def check_item(it):
        if it[0] == "col":
            check_col(it[1])
        elif it[2] != "*":
            check_col(it[2])
            if it[1] in ("SUM", "AVG") and types[it[2]] != "num":
                raise QueryError(f"{it[1]} needs a numeric column")

    def typecheck(node):
        t = node[0]
        if t in ("or", "and"):
            typecheck(node[1]); typecheck(node[2])
        elif t == "not":
            typecheck(node[1])
        elif t == "isnull":
            if node[1][0] == "col":
                check_col(node[1][1])
        else:
            kinds = []
            for o in node[2:]:
                if o[0] == "col":
                    check_col(o[1]); kinds.append(types[o[1]])
                else:
                    kinds.append(o[1])
            if kinds[0] != kinds[1]:
                raise QueryError("cannot compare number with string")

    sel = q["select"]
    if sel != "*":
        for it in sel:
            check_item(it)
    for c in q["group"]:
        check_col(c)
    for key, _ in q["order"]:
        check_item(key)
    if q["where"] is not None:
        typecheck(q["where"])

    aggregating = bool(q["group"]) or (sel != "*" and any(it[0] == "agg" for it in sel))
    if aggregating:
        if sel == "*":
            raise QueryError("SELECT * cannot be grouped")
        for it in sel:
            if it[0] == "col" and it[1] not in q["group"]:
                raise QueryError(f"column {it[1]!r} must be grouped")
        for key, _ in q["order"]:
            if key[0] == "col" and key[1] not in q["group"]:
                raise QueryError(f"ORDER BY {key[1]!r} must be grouped or aggregated")

    def val(o, rec):
        if o[0] == "lit":
            return o[2]
        v = rec[o[1]]
        return None if v is None else v[0]

    def ev(node, rec):
        t = node[0]
        if t == "or":
            a, b = ev(node[1], rec), ev(node[2], rec)
            if a is True or b is True:
                return True
            return None if a is None or b is None else False
        if t == "and":
            a, b = ev(node[1], rec), ev(node[2], rec)
            if a is False or b is False:
                return False
            return None if a is None or b is None else True
        if t == "not":
            a = ev(node[1], rec)
            return None if a is None else not a
        if t == "isnull":
            isn = node[1][0] == "col" and rec[node[1][1]] is None
            return isn != node[2]
        a, b = val(node[2], rec), val(node[3], rec)
        if a is None or b is None:
            return None
        return {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[node[1]]

    rows = [r for r in recs if q["where"] is None or ev(q["where"], r) is True]

    def agg(it, group):
        fn, arg = it[1], it[2]
        if arg == "*":
            return Agg(len(group))
        vals = [r[arg] for r in group if r[arg] is not None]
        if fn == "COUNT":
            return Agg(len(vals))
        if not vals:
            return None
        if fn == "MIN":
            return min(vals, key=lambda v: v[0])
        if fn == "MAX":
            return max(vals, key=lambda v: v[0])
        s = sum((v[0] for v in vals), Decimal(0))
        return Agg(s if fn == "SUM" else s / len(vals))

    # each output row: (dict key -> sortable value, list of output values)
    out = []
    if aggregating:
        groups = {}
        for r in rows:
            k = tuple(None if r[c] is None else r[c][0] for c in q["group"])
            groups.setdefault(k, []).append(r)
        glist = list(groups.values())
        if not q["group"]:
            glist = [rows]
        for g in glist:
            def get(it, g=g):
                return g[0][it[1]] if it[0] == "col" else agg(it, g)
            out.append((get, [get(it) for it in sel]))
        cols = [it[1] if it[0] == "col" else f"{it[1]}({it[2]})" for it in sel]
    else:
        items = [("col", h) for h in header] if sel == "*" else sel
        for r in rows:
            def get(it, r=r):
                return r[it[1]]
            out.append((get, [get(it) for it in items]))
        cols = [it[1] for it in items]

    def sortval(v):
        if v is None:
            return None
        return v.value if isinstance(v, Agg) else v[0]

    for key, desc in reversed(q["order"]):
        def k(row, key=key, desc=desc):
            sv = sortval(row[0](key))
            return (0,) if sv is None else (1, sv)
        out.sort(key=k, reverse=desc)
    if q["limit"] is not None:
        out = out[:q["limit"]]

    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, Agg) and isinstance(v.value, int):
            return str(v.value)
        if isinstance(v, Agg):
            d = v.value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            s = format(d, "f")
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return "0" if s in ("-0", "") else s
        return v[1]

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for _, vals in out:
        w.writerow([fmt(v) for v in vals])
    return buf.getvalue()
