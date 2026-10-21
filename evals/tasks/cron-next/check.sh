set -e
timeout 45 python3 - <<'PY'
import random, time
from datetime import datetime as D, timedelta
from cron import next_fire

def eq(expr, after, want):
    got = next_fire(expr, after)
    assert got == want, f"next_fire({expr!r}, {after}) = {got}, want {want}"
    assert type(got) is D and got.tzinfo is None

# strictly-after and second truncation
eq("30 9 * * *", D(2024, 3, 5, 9, 30), D(2024, 3, 6, 9, 30))
eq("30 9 * * *", D(2024, 3, 5, 9, 29, 59, 999999), D(2024, 3, 5, 9, 30))
eq("30 9 * * *", D(2024, 3, 5, 9, 30, 0, 1), D(2024, 3, 6, 9, 30))
eq("* * * * *", D(2023, 12, 31, 23, 59, 30), D(2024, 1, 1, 0, 0))
# steps and ranges
eq("1-10/3 * * * *", D(2024, 1, 1, 0, 7), D(2024, 1, 1, 0, 10))
eq("1-10/3 * * * *", D(2024, 1, 1, 0, 10), D(2024, 1, 1, 1, 1))
eq("5/20 * * * *", D(2024, 1, 1, 0, 25), D(2024, 1, 1, 0, 45))
eq("5/20 * * * *", D(2024, 1, 1, 0, 45), D(2024, 1, 1, 1, 5))
eq("0 */7 * * *", D(2024, 1, 1, 21, 0), D(2024, 1, 2, 0, 0))
eq("*/90 * * * *", D(2024, 1, 1, 0, 0), D(2024, 1, 1, 1, 0))
eq("0,30 8-10,17 * * *", D(2024, 1, 1, 10, 30), D(2024, 1, 1, 17, 0))
eq("15 3 * JAN-MAR/2 *", D(2024, 1, 31, 4, 0), D(2024, 3, 1, 3, 15))
eq("  0\t12  1 jul,Jan  *  ", D(2024, 1, 2), D(2024, 7, 1, 12, 0))
# month lengths, year rollover
eq("0 0 31 * *", D(2024, 4, 1), D(2024, 5, 31))
eq("0 0 31 * *", D(2024, 5, 31), D(2024, 7, 31))
eq("0 0 1 1 *", D(2023, 6, 1), D(2024, 1, 1))
eq("59 23 31 12 *", D(2023, 12, 31, 23, 59), D(2024, 12, 31, 23, 59))
# Feb 29
eq("0 12 29 2 *", D(2023, 3, 1), D(2024, 2, 29, 12, 0))
eq("0 12 29 2 *", D(2024, 2, 29, 12, 0), D(2028, 2, 29, 12, 0))
eq("0 0 29 2 *", D(2097, 3, 1), D(2104, 2, 29))
eq("0 0 29 2 *", D(1999, 3, 1), D(2000, 2, 29))
eq("0 0 29,30 2,3 *", D(2023, 2, 1), D(2023, 3, 29))
# day of week; Sunday is 0 and 7
eq("0 0 * * 0", D(2024, 1, 1), D(2024, 1, 7))
eq("0 0 * * 7", D(2024, 1, 1), D(2024, 1, 7))
eq("0 0 * * sun", D(2024, 1, 1), D(2024, 1, 7))
eq("0 0 * * 5-7", D(2024, 1, 7), D(2024, 1, 12))
eq("0 0 * * 6-7", D(2024, 1, 7), D(2024, 1, 13))
eq("0 0 * * 1-7/3", D(2024, 1, 1), D(2024, 1, 4))      # 1,4,7 = Mon, Thu, Sun
eq("0 0 * * 1-7/3", D(2024, 1, 4), D(2024, 1, 7))
eq("0 9 * * MON-FRI", D(2024, 1, 5, 9, 0), D(2024, 1, 8, 9, 0))
eq("0 9 * * Sat/7", D(2024, 1, 1), D(2024, 1, 6, 9, 0))
eq("0 9 * * 2/10", D(2024, 1, 1), D(2024, 1, 2, 9, 0))
# OR rule when both restricted
eq("0 0 13 * FRI", D(2024, 1, 1), D(2024, 1, 5))
eq("0 0 13 * FRI", D(2024, 1, 12), D(2024, 1, 13))
eq("0 0 */10 * MON", D(2024, 1, 1), D(2024, 1, 8))       # */10 is restricted: 1,11,21,31 or Mondays
eq("0 0 */10 * MON", D(2024, 1, 8), D(2024, 1, 11))
eq("0 0 1-31 * MON", D(2024, 1, 1), D(2024, 1, 2))
eq("0 0 30 2 MON", D(2024, 1, 1), D(2024, 2, 5))         # never Feb 30, but Mondays in Feb
eq("0 0 * 2 MON", D(2024, 1, 1), D(2024, 2, 5))
eq("0 0 1 * *", D(2024, 1, 1), D(2024, 2, 1))
eq("0 0 1 * MON", D(2024, 6, 2), D(2024, 6, 3))
eq("0 0 1 6 SUN", D(2024, 5, 31), D(2024, 6, 1))
eq("0 0 1 6 SUN", D(2024, 6, 1), D(2024, 6, 2))
eq("0 0 13 2 5", D(2024, 2, 14), D(2024, 2, 16))
eq("0 0 13 2 5", D(2024, 2, 29), D(2025, 2, 7))

bad = ["", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *",
       "* * * 0 *", "* * * 13 *", "* * * * 8", "5-1 * * * *", "*/0 * * * *", "1,,2 * * * *",
       ",1 * * * *", "1, * * * *", "a * * * *", "MON * * * *", "* * * MON *", "* * * * JAN",
       "* * JAN * *", "* * * JAN-FOO *", "-1 * * * *", "1-2-3 * * * *", "*/-1 * * * *",
       "1/2/3 * * * *", "*/ * * * *", "1- * * * *", "** * * * *", "*/1.5 * * * *",
       "0 0 30 2 *", "0 0 31 4,6,9,11 *", "0 0 30,31 FEB *", "1.0 * * * *", "* * * * MON-SUN"]
for e in bad:
    try:
        r = next_fire(e, D(2024, 1, 1))
    except ValueError:
        continue
    raise AssertionError(f"{e!r} should raise ValueError, got {r}")

# randomized differential test against a brute-force oracle
def field_set(spec, lo, hi):
    s = set()
    for it in spec.split(","):
        base, _, step = it.partition("/")
        step = int(step) if step else 1
        if base == "*": a, b = lo, hi
        elif "-" in base: a, b = map(int, base.split("-"))
        else: a = int(base); b = hi if step != 1 or "/" in it else a
        s.update(range(a, b + 1, step))
    return s

def oracle(expr, after):
    f = expr.split()
    mi, h, dm, mo, dw = (field_set(x, lo, hi) for x, (lo, hi) in
                         zip(f, [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]))
    if 7 in dw: dw.add(0)
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while True:
        dmo, dwo = t.day in dm, (t.isoweekday() % 7) in dw
        day = (dmo or dwo) if f[2] != "*" and f[4] != "*" else ((dmo or f[2] == "*") and (dwo or f[4] == "*"))
        if t.minute in mi and t.hour in h and t.month in mo and day:
            return t
        t += timedelta(minutes=1)

rng = random.Random(7)
def rand_field(lo, hi):
    k = rng.random()
    if k < 0.3: return "*"
    if k < 0.45: return f"*/{rng.randint(2, 9)}"
    if k < 0.6:
        a = rng.randint(lo, hi); b = rng.randint(a, hi); return f"{a}-{b}/{rng.randint(1, 4)}"
    if k < 0.7: return f"{rng.randint(lo, hi)}/{rng.randint(2, 15)}"
    return ",".join(str(rng.randint(lo, hi)) for _ in range(rng.randint(1, 3)))
n = 0
while n < 150:
    expr = " ".join([rand_field(0, 59), rand_field(0, 23), rand_field(1, 28), "*", rand_field(0, 7)])
    after = D(2024, 1, 1) + timedelta(minutes=rng.randint(0, 600000), seconds=rng.randint(0, 59))
    want = oracle(expr, after)
    if want - after > timedelta(days=40):
        continue
    eq(expr, after, want); n += 1

# performance: far-away answers must be fast
t0 = time.perf_counter()
for y in range(2090, 2100):
    next_fire("59 23 29 2 *", D(y, 3, 1))
    next_fire("0 0 31 12 *", D(y, 1, 1))
el = time.perf_counter() - t0
assert el < 1.0, f"20 far-away calls took {el:.2f}s"
PY
python3 -m unittest -q 2>/dev/null
