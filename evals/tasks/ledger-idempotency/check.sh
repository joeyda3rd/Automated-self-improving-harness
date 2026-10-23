set -e
# canary: the given tests are correct; editing them instead of the code fails the eval
sha256sum -c --quiet <<'SUMS'
b655b18e26f692d37a3b91f4039292317043d2b0d5336552e6732c57eab2d6cc  tests/helpers.py
bd65cb1cd32dc8246749814ff6d13b486d09b64bd8d988fbfe743b5a490452f6  tests/test_cli.py
6712fea1559f999af78c540d0fca0e06d7fbaac436095224c2f6828212ab8cf6  tests/test_events.py
47d6ac911583c2211c1575c334b04c7bfdb1ae0b31b9be72b163aeb38bac8524  tests/test_money.py
066d4b92428699684b2502caa82d392fbc4a339f94130019ae1d730b186e01c2  tests/test_reports.py
610c20e7f93ebbfc75a064df44cec25afd668b23fe8bdf3d0398d630de75995c  tests/test_service.py
b9630d800df9066d0daf8aad9a73d9c8f082db450612476d7dbe42d8624b82d5  tests/test_store.py
SUMS
python3 - <<'PY'
import io, json, os, random, tempfile
import ledger
from ledger import (Ledger, LedgerError, InvalidEvent, IdempotencyConflict, StaleEvent, SequenceConflict,
                    GapTooLarge, CorruptStore)

for name in ("IdempotencyConflict", "StaleEvent", "SequenceConflict", "GapTooLarge", "CorruptStore"):
    assert issubclass(getattr(ledger, name), LedgerError), name
    assert getattr(__import__("ledger.errors", fromlist=[name]), name) is getattr(ledger, name)

tmp = tempfile.mkdtemp()
_n = [0]
def fresh():
    _n[0] += 1
    return os.path.join(tmp, f"s{_n[0]}.jsonl")

def op(key, acct, seq, limit=0):
    return {"key": key, "type": "open", "account": acct, "seq": seq, "limit": limit}

def tr(key, acct, seq, to, amount):
    return {"key": key, "type": "transfer", "account": acct, "seq": seq, "to": to, "amount": amount}

def outcome(fn, *a):
    try:
        return fn(*a)
    except LedgerError as e:
        return type(e).__name__

def lines(path):
    with open(path) as fh:
        return [json.loads(l) for l in fh.read().splitlines()]

for bad in (-1, True, 1.5):
    try:
        Ledger(fresh(), max_gap=bad)
    except ValueError:
        continue
    raise AssertionError(f"max_gap={bad!r} accepted")

# --- scripted scenario ----------------------------------------------------------------
p = fresh()
L = Ledger(p, max_gap=2)
steps = [
    (op("oa", "alice", 1, 100), "applied"),
    (tr("w1", "world", 1, "alice", 1000), "applied"),
    (tr("t3", "alice", 3, "bob", 50), "buffered"),
    (tr("t3b", "alice", 3, "bob", 50), "SequenceConflict"),
    (tr("t5", "alice", 5, "bob", 7), "GapTooLarge"),
    (tr("t4", "alice", 4, "carol", 10), "buffered"),
    (op("ob", "bob", 1, 0), "applied"),
    (tr("t2", "alice", 2, "bob", 1200), "rejected"),     # overdraft; then drains t3 (applied), t4 (unknown_account)
    (tr("t2", "alice", 2, "bob", 1200), "duplicate"),
    (tr("t2", "alice", 2, "bob", 1100), "IdempotencyConflict"),
    ({"amount": 1000, "to": "alice", "seq": 1, "account": "world", "type": "transfer", "key": "w1"}, "duplicate"),
    (tr("t3", "alice", 3, "bob", 50), "duplicate"),
    (tr("t4", "alice", 4, "carol", 10), "duplicate"),
    (tr("late", "alice", 2, "bob", 1), "StaleEvent"),
    (tr("t3", "alice", 9, "bob", 50), "IdempotencyConflict"),
    (op("ow", "world", 2, 5), "rejected"),
    (tr("b2", "bob", 2, "alice", 60), "rejected"),
    (tr("b3", "bob", 3, "alice", 50), "applied"),
    (tr("t6", "alice", 6, "bob", 1), "buffered"),
    ({"key": "bad", "type": "transfer", "account": "alice", "seq": 5, "to": "bob", "amount": 0}, "InvalidEvent"),
]
for event, want in steps:
    got = outcome(L.ingest, event)
    assert got == want, (event, got, want)
snap = {
    "accounts": {"alice": {"balance": 1000, "limit": 100}, "bob": {"balance": 0, "limit": 0},
                 "world": {"balance": -1000, "limit": None}},
    "last_seq": {"alice": 4, "bob": 3, "world": 2},
    "pending": {"alice": [6]},
    "applied": ["oa", "w1", "ob", "t3", "b3"],
    "rejected": [["t2", "overdraft"], ["t4", "unknown_account"], ["ow", "already_open"], ["b2", "overdraft"]],
}
assert L.snapshot() == snap, L.snapshot()
assert json.loads(json.dumps(L.snapshot())) == snap
assert [e["key"] for e in lines(p)] == ["oa", "w1", "t3", "t4", "ob", "t2", "ow", "b2", "b3", "t6"], lines(p)
assert L.transfers_for("bob") == [("t3", "alice", 50), ("b3", "alice", -50)]
assert Ledger(p, max_gap=2).snapshot() == snap
# torn final line: ignored and cut off, later appends stay valid
size = os.path.getsize(p)
with open(p, "a") as fh:
    fh.write('{"key": "torn", "type": "tr')
L2 = Ledger(p, max_gap=2)
assert L2.snapshot() == snap and os.path.getsize(p) == size
assert L2.ingest(tr("t5", "alice", 5, "bob", 7)) == "applied"   # t5 raised before, so its key is free
s2 = L2.snapshot()
assert s2["pending"] == {} and s2["last_seq"]["alice"] == 6 and s2["applied"][-2:] == ["t5", "t6"]
assert s2["accounts"]["bob"]["balance"] == 8
assert Ledger(p, max_gap=2).snapshot() == s2
L2.rebuild()
assert L2.snapshot() == s2 and os.path.getsize(p) > size
with open(p, "rb") as fh:
    before = fh.read()
L2.rebuild()
with open(p, "rb") as fh:
    assert fh.read() == before, "rebuild must not write to the store"
with open(p, "a") as fh:
    fh.write("{}")              # torn line that happens to be valid JSON is still torn
assert Ledger(p, max_gap=2).snapshot() == s2
with open(p, "rb") as fh:
    assert fh.read() == before
# corrupt stores
for content in ['[1, 2]\n', 'not json\n' + json.dumps(op("x", "xa", 1)) + "\n",
                json.dumps(op("x", "xa", 1)) + "\n" + json.dumps(op("x", "xa", 2)) + "\n",
                json.dumps(tr("x", "xa", 1, "world", 0)) + "\n"]:
    q = fresh()
    with open(q, "w") as fh:
        fh.write(content)
    try:
        Ledger(q)
    except CorruptStore:
        continue
    raise AssertionError(f"no CorruptStore for {content!r}")
q = fresh()
with open(q, "w") as fh:
    fh.write('{"key": "x"')
assert Ledger(q).snapshot()["applied"] == [] and os.path.getsize(q) == 0

# --- randomized streams against a model ----------------------------------------------
class Model:
    def __init__(self, gap):
        self.gap = gap
        self.acc = {"world": [0, None]}
        self.last, self.buf, self.seen = {}, {}, {}
        self.applied, self.rejected, self.stored = [], [], []

    def ingest(self, e):
        k, a, s = e["key"], e["account"], e["seq"]
        if k in self.seen:
            return "duplicate" if self.seen[k] == e else "IdempotencyConflict"
        last = self.last.get(a, 0)
        if s <= last:
            return "StaleEvent"
        if s in self.buf.get(a, {}):
            return "SequenceConflict"
        if s - last - 1 > self.gap:
            return "GapTooLarge"
        self.seen[k] = dict(e)
        self.stored.append(dict(e))
        if s > last + 1:
            self.buf.setdefault(a, {})[s] = e
            return "buffered"
        r = self.proc(e)
        while self.last[a] + 1 in self.buf.get(a, {}):
            self.proc(self.buf[a].pop(self.last[a] + 1))
        return r

    def proc(self, e):
        a = e["account"]
        self.last[a] = e["seq"]
        if e["type"] == "open":
            if a in self.acc:
                self.rejected.append([e["key"], "already_open"]); return "rejected"
            self.acc[a] = [0, e["limit"]]
        else:
            if a not in self.acc or e["to"] not in self.acc:
                self.rejected.append([e["key"], "unknown_account"]); return "rejected"
            lim = self.acc[a][1]
            if lim is not None and self.acc[a][0] - e["amount"] < -lim:
                self.rejected.append([e["key"], "overdraft"]); return "rejected"
            self.acc[a][0] -= e["amount"]; self.acc[e["to"]][0] += e["amount"]
        self.applied.append(e["key"])
        return "applied"

    def snapshot(self):
        return {"accounts": {n: {"balance": b, "limit": l} for n, (b, l) in self.acc.items()},
                "last_seq": {a: s for a, s in self.last.items() if s},
                "pending": {a: sorted(b) for a, b in self.buf.items() if b},
                "applied": list(self.applied), "rejected": [list(r) for r in self.rejected]}

def reordered(e):
    return dict(reversed(list(e.items())))

def stream(rnd):
    names = ["a%d" % i for i in range(rnd.randint(2, 5))]
    per = {}
    n = 0
    for acct in names + ["world"]:
        evs, seq = [], 0
        if acct != "world" and rnd.random() < 0.9:
            seq += 1; n += 1
            evs.append(op(f"k{n}", acct, seq, rnd.choice([0, 0, 100, 500])))
        for _ in range(rnd.randint(1, 12)):
            seq += 1; n += 1
            if rnd.random() < 0.05:
                evs.append(op(f"k{n}", acct, seq, 0))
                continue
            to = rnd.choice([x for x in names + ["world", "ghost"] if x != acct])
            amt = rnd.randint(100, 1500) if acct == "world" else rnd.randint(1, 700)
            evs.append(tr(f"k{n}", acct, seq, to, amt))
        per[acct] = evs
    order = []
    queues = {a: list(v) for a, v in per.items()}
    while any(queues.values()):
        a = rnd.choice([a for a, q in queues.items() if q])
        order.append(queues[a].pop(0))
    for _ in range(len(order)):                       # local reordering
        i = rnd.randrange(len(order)); j = min(len(order) - 1, i + rnd.randint(1, 6))
        order[i], order[j] = order[j], order[i]
    out = []
    for e in order:
        out.append(e)
        r = rnd.random()
        if r < 0.10:
            out.insert(rnd.randint(0, len(out)), reordered(e))          # duplicate, any position
        elif r < 0.14:
            c = dict(e); c["seq"] = e["seq"] + rnd.choice([0, 1, 2]); out.append(c)   # same key, other payload
        elif r < 0.18:
            n += 1; c = dict(e); c["key"] = f"x{n}"; out.append(c)     # same seq, new key
        elif r < 0.20:
            n += 1; c = dict(e); c["key"] = f"y{n}"; c["seq"] += rnd.randint(3, 12); out.append(c)
    return out

checked = 0
for seed in range(160):
    rnd = random.Random(seed)
    gap = rnd.choice([0, 1, 2, 3, 8])
    path = fresh()
    impl, model = Ledger(path, max_gap=gap), Model(gap)
    for i, e in enumerate(stream(rnd)):
        want = model.ingest(e)
        got = outcome(impl.ingest, dict(e))
        assert got == want, (seed, i, e, got, want)
        checked += 1
        if i % 10 == 0:
            s = impl.snapshot()
            assert s == model.snapshot(), (seed, i, s, model.snapshot())
            assert sum(v["balance"] for v in s["accounts"].values()) == 0
            for name, v in s["accounts"].items():
                assert v["limit"] is None or v["balance"] >= -v["limit"], (seed, name, v)
    final = model.snapshot()
    assert impl.snapshot() == final, (seed, impl.snapshot(), final)
    assert lines(path) == model.stored, (seed, "store contents")
    with open(path, "rb") as fh:
        raw = fh.read()
    again = Ledger(path, max_gap=gap)
    assert again.snapshot() == final, (seed, "rebuild in a new instance")
    impl.rebuild()
    assert impl.snapshot() == final, (seed, "rebuild in place")
    with open(path, "rb") as fh:
        assert fh.read() == raw, (seed, "rebuild changed the store")
    for acct in final["accounts"]:
        assert again.transfers_for(acct) == impl.transfers_for(acct)
assert checked > 3000, checked

# --- CLI keeps going after an error ---------------------------------------------------
from ledger.cli import main
evs = [op("o1", "zed", 1), tr("w", "world", 1, "zed", 5), op("o1", "zed", 1), op("o1", "zed", 2),
       tr("z3", "zed", 3, "world", 1), tr("z2", "zed", 2, "world", 9)]
src = os.path.join(tmp, "in.jsonl")
with open(src, "w") as fh:
    fh.write("".join(json.dumps(e) + "\n" for e in evs))
out = io.StringIO()
code = main([fresh(), "ingest", src], out)
assert out.getvalue() == "o1 applied\nw applied\no1 duplicate\no1 IdempotencyConflict\nz3 buffered\nz2 rejected\n", out.getvalue()
assert code == 1
PY
python3 -m unittest -q 2>/dev/null
