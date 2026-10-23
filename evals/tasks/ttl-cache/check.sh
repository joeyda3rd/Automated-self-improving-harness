set -e
python3 - <<'PY'
from cache import TTLCache

class Clock:
    t = 0.0
    def __call__(self):
        return self.t

for args in [(0, 1), (1, 0), (2, -1)]:
    try:
        TTLCache(*args)
    except ValueError:
        continue
    raise AssertionError(f"accepted {args}")

c = Clock(); k = TTLCache(2, 10, clock=c)
k.put("a", 1); c.t = 9.999
assert k.get("a") == 1
c.t = 10
assert k.get("a") is None and "a" not in k and len(k) == 0, "expires at exactly ttl; get must not extend life"

c = Clock(); k = TTLCache(2, 10, clock=c)
k.put("a", 1); k.put("b", 2); k.get("a"); k.put("c", 3)
assert "b" not in k and k.get("a") == 1 and k.get("c") == 3, "get refreshes recency, LRU evicted"

c = Clock(); k = TTLCache(2, 10, clock=c)
k.put("a", 1); k.put("b", 2)
assert "a" in k                       # must not refresh recency
k.put("c", 3)
assert "a" not in k and "b" in k, "membership test must not change recency"

c = Clock(); k = TTLCache(3, 10, clock=c)
k.put("old", 0); c.t = 5; k.put("x", 1); k.put("y", 2); k.get("old"); c.t = 11
k.put("z", 3)                         # 'old' expired: drop it, keep the LRU live entry 'x'
assert k.get("x") == 1 and k.get("y") == 2 and k.get("z") == 3 and len(k) == 3

c = Clock(); k = TTLCache(2, 10, clock=c)
k.put("a", 1); k.put("b", 2); c.t = 8; k.put("a", 9)   # update: no eviction, lifetime reset, MRU
assert len(k) == 2 and k.get("a") == 9
c.t = 12
assert "b" not in k and k.get("a") == 9 and len(k) == 1
k.put("c", 3); k.put("d", 4)
assert "a" not in k and "c" in k and "d" in k
assert k.get("missing", "dflt") == "dflt"
PY
python3 -m unittest -q 2>/dev/null
