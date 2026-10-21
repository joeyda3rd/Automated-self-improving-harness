set -e
python3 - <<'PY'
import gc, os, random, sys, threading, time, weakref
from ratelimit import RateLimiter


class Clock:
    def __init__(self, t=0.0):
        self.t = t
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.t


def eq(got, want, what):
    assert got == want, f"{what}: got {got!r}, want {want!r}"


# --- validation ---
for args, kw in [((0, 1), {}), ((-1, 1), {}), ((1, 0), {}), ((1, -2), {}), ((1, 1), {"overrides": {"k": 0}})]:
    try:
        RateLimiter(*args, clock=Clock(), **kw)
    except ValueError:
        continue
    raise AssertionError(f"RateLimiter{args} {kw} accepted")
rl = RateLimiter(5, 1, clock=Clock())
for bad in (0, -1, -0.5):
    for call in (lambda: rl.acquire("k", bad), lambda: rl.try_acquire_many([("j", 1), ("k", bad)]), lambda: rl.set_capacity("k", bad)):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError(f"accepted non-positive amount {bad}")
eq(rl.available("j"), 5.0, "invalid try_acquire_many must not consume anything")
eq(len(rl), 0, "len after only invalid calls")

# --- exact refill arithmetic ---
c = Clock(); rl = RateLimiter(4, 0.5, clock=c)
eq(rl.available("a"), 4.0, "fresh bucket is full"); eq(len(rl), 0, "available must not create a bucket")
eq(rl.acquire("a", 4), True, "take full capacity")
eq(rl.acquire("a", 0.25), False, "empty bucket")
c.t = 1.0; eq(rl.available("a"), 0.5, "refill 1s at 0.5/s")
eq(rl.acquire("a", 0.75), False, "0.5 < 0.75")
c.t = 1.5; eq(rl.acquire("a", 0.75), True, "0.75 available at t=1.5")
eq(rl.available("a"), 0.0, "fractional debit")
c.t = 3.0; eq(rl.acquire("a", 0.5), True, "0.75 refilled"); eq(rl.available("a"), 0.25, "fractional remainder")
c.t = 100.0; eq(rl.available("a"), 4.0, "refill is capped at capacity")
eq(rl.acquire("a", 4.5), False, "request above capacity never succeeds")
eq(rl.acquire("a", 4), True, "after cap, exactly capacity"); c.t = 101.0; eq(rl.available("a"), 0.5, "no banking above capacity")

# --- overrides and set_capacity ---
c = Clock(); rl = RateLimiter(2, 1, clock=c, overrides={"vip": 10})
eq(rl.available("vip"), 10.0, "override capacity"); eq(rl.available("x"), 2.0, "default capacity")
eq(rl.acquire("vip", 9), True, "vip burst"); eq(rl.acquire("x", 3), False, "default capacity applies")
rl.set_capacity("vip", 4)             # level 1 < 4: kept, not clamped
eq(rl.available("vip"), 1.0, "lowering capacity above the level keeps tokens")
c.t = 2.0; eq(rl.acquire("vip", 3), True, "refills to new capacity 4"); eq(rl.available("vip"), 0.0, "after debit")
c.t = 3.5; rl.set_capacity("vip", 1); eq(rl.available("vip"), 1.0, "clamped to new lower capacity")
eq(len(rl), 0, "a bucket clamped to full is discarded")
rl.acquire("y", 1)                     # y: level 1 of 2
rl.set_capacity("y", 0.5); eq(rl.available("y"), 0.5, "clamp to 0.5"); eq(len(rl), 0, "clamped-full bucket discarded")
c.t = 10.0; eq(rl.acquire("z", 1), True, "z"); c.t = 11.0
rl.set_capacity("z", 8); eq(rl.available("z"), 8.0, "a full bucket (old cap) starts fresh at the new capacity")
rl.set_capacity("fresh", 3); eq(rl.available("fresh"), 3.0, "set_capacity on unknown key")
eq(rl.acquire("fresh", 3), True, "new capacity used for new key"); eq(rl.available("x"), 2.0, "others unaffected")

# --- try_acquire_many ---
class K:
    pass
k1, k2 = K(), K()
c = Clock(); rl = RateLimiter(3, 1, clock=c, overrides={"small": 1})
eq(rl.try_acquire_many([]), True, "empty request list")
eq(rl.try_acquire_many([(1, 2), ("a", 2), (k1, 1)]), True, "unorderable keys")
eq(rl.try_acquire_many([(1, 1), ("a", 1), (k1, 1), ("small", 2)]), False, "one key short")
eq([rl.available(k) for k in (1, "a", k1, "small")], [1.0, 1.0, 2.0, 1.0], "failed batch changed nothing")
eq(rl.try_acquire_many([(k2, 2), (k2, 2)]), False, "duplicate keys are summed (4 > 3)")
eq(rl.available(k2), 3.0, "failed duplicate batch changed nothing")
eq(rl.try_acquire_many([(k2, 1.5), ("small", 1), (k2, 1.5)]), True, "duplicates summed to exactly capacity")
eq((rl.available(k2), rl.available("small")), (0.0, 0.0), "both debited")
eq(rl.try_acquire_many(iter([("a", 1), (1, 1)])), True, "any iterable of pairs")

# --- eviction is exact and memory is released ---
c = Clock(); rl = RateLimiter(2, 0.5, clock=c)
rl.acquire("k", 1)                    # full again at t=2
c.t = 1.5; rl.acquire("o", 1)         # full at 3.5
eq(len(rl), 2, "two partial buckets")
c.t = 2.0; rl.acquire("p", 2)          # p empty, full at 6
eq(len(rl), 2, "k is full at t=2 exactly and must be gone")
rl.acquire("q", 5)                    # fails; a new full bucket is not stored
eq(len(rl), 2, "failed acquire on a new key stores nothing")
c.t = 3.5; rl.try_acquire_many([("p", 0.25)]); eq(len(rl), 1, "o expired at 3.5")
c.t = 6.25; rl.try_acquire_many([]); eq(len(rl), 1, "p is full only at 6.5"); c.t = 6.5; rl.try_acquire_many([]); eq(len(rl), 0, "even an empty try_acquire_many evicts")

c = Clock(); rl = RateLimiter(1, 0.25, clock=c)
keys = [K() for _ in range(2000)]
refs = [weakref.ref(k) for k in keys]
for k in keys:
    rl.acquire(k, 0.5)
eq(len(rl), 2000, "2000 live buckets")
del keys, k
c.t = 2.0; rl.acquire("last", 1); gc.collect()
eq(len(rl), 1, "all half-empty buckets refilled by t=2")
alive = sum(r() is not None for r in refs)
eq(alive, 0, "limiter still references keys of evicted buckets")

# --- clock is read exactly once per call ---
c = Clock(); rl = RateLimiter(2, 1, clock=c)
rl.acquire("a"); rl.acquire("b", 5); rl.try_acquire_many([("a", 1), ("b", 1), ("c", 1)]); rl.try_acquire_many([])
rl.available("a"); rl.set_capacity("a", 3); len(rl)
eq(c.calls, 6, "clock() calls for 6 clock-reading calls + len")

# --- performance: many keys, continuous eviction ---
c = Clock(); rl = RateLimiter(1, 2 ** -10, clock=c)
start = time.perf_counter()
for i in range(50000):
    c.t = i / 16
    assert rl.acquire(i, 1)
    if i % 1000 == 0:
        assert time.perf_counter() - start < 10, f"too slow: only {i} of 50000 acquires on distinct keys in 10s"
elapsed = time.perf_counter() - start
eq(len(rl), 16384, "live buckets after 50k distinct keys")
assert elapsed < 10, f"50k acquires on distinct keys took {elapsed:.1f}s (limit 10s)"

# --- concurrency ---
sys.setswitchinterval(1e-6)


def run_threads(targets, timeout=20):
    errors = []

    def wrap(fn):
        def go():
            try:
                fn()
            except BaseException as e:  # noqa
                errors.append(repr(e))
        return go
    ts = [threading.Thread(target=wrap(fn), daemon=True) for fn in targets]
    for t in ts:
        t.start()
    deadline = time.monotonic() + timeout
    for t in ts:
        t.join(max(0.0, deadline - time.monotonic()))
    if any(t.is_alive() for t in ts):
        print("DEADLOCK: threads still running after %ss" % timeout, file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)
    assert not errors, errors[:3]


# over-admission: 16 threads x 5000 ops on 4 keys, frozen clock
c = Clock(); keys4 = ["k0", "k1", "k2", "k3"]
rl = RateLimiter(1000, 1, clock=c)
tallies = []


def worker(seed):
    rnd = random.Random(seed); got = dict.fromkeys(keys4, 0); tallies.append(got)

    def fn():
        for _ in range(5000):
            if rnd.random() < 0.5:
                k = rnd.choice(keys4)
                if rl.acquire(k):
                    got[k] += 1
            else:
                a, b = rnd.sample(keys4, 2)
                if rl.try_acquire_many([(a, 1), (b, 1)]):
                    got[a] += 1; got[b] += 1
    return fn


run_threads([worker(s) for s in range(16)])
for k in keys4:
    granted = sum(t[k] for t in tallies)
    assert granted <= 1000, f"over-admission on {k}: {granted} > 1000"
    eq(granted + rl.available(k), 1000.0, f"tokens lost or created on {k}")
    eq(rl.available(k), 0.0, f"{k} should be drained")

# atomicity + deadlock: batches over A and B in both orders always fail (B is empty); A must never look debited
c = Clock(); rl = RateLimiter(1, 1, clock=c, overrides={"A": 2})
assert rl.acquire("B", 1)
seen = []


def batcher(order):
    def fn():
        for _ in range(5000):
            req = [("A", 1), ("B", 1)] if order else [("B", 1), ("A", 1)]
            if rl.try_acquire_many(req):
                raise AssertionError("batch with empty B succeeded")
    return fn


def observer():
    for _ in range(5000):
        v = rl.available("A")
        if v != 2.0:
            seen.append(v)


run_threads([batcher(i % 2) for i in range(8)] + [observer for _ in range(8)])
assert not seen, f"partial debit of A observed during failing batches: {seen[:5]}"
eq(rl.available("A"), 2.0, "A untouched"); eq(rl.available("B"), 0.0, "B still empty")

# deadlock-prone pattern: overlapping batches in opposite key orders that succeed (slow refill, frozen clock)
c = Clock(); rl = RateLimiter(10 ** 9, 1, clock=c)
pairs = [("x", "y"), ("y", "z"), ("z", "x"), ("y", "x"), ("z", "y"), ("x", "z")]
run_threads([(lambda p=p: [rl.try_acquire_many([(p[0], 1), (p[1], 1)]) for _ in range(5000)]) for p in pairs * 2])
total = sum(10 ** 9 - rl.available(k) for k in "xyz")
eq(total, 12 * 5000 * 2, "every batch debited both keys")
print("ok")
PY
python3 -m unittest -q 2>/dev/null
