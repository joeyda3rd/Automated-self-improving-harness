"""Thread-safe keyed token-bucket rate limiter with an injected clock."""
import heapq
import itertools
import math
import threading
import time


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError(f"{name} must be a positive number, got {value!r}")
    return value


class RateLimiter:
    def __init__(self, capacity, rate, clock=time.monotonic, overrides=None):
        self._capacity = _positive(capacity, "capacity")
        self._rate = _positive(rate, "rate")
        self._clock = clock
        self._caps = {k: _positive(v, "capacity") for k, v in (overrides or {}).items()}
        self._buckets = {}            # key -> (tokens, last, seq)
        self._heap = []               # (full_at, seq, key); seq is unique so keys are never compared
        self._seq = itertools.count()
        self._lock = threading.Lock()

    # -- internals (lock held) --
    def _cap(self, key):
        return self._caps.get(key, self._capacity)

    def _level(self, key, t):
        cap = self._cap(key)
        b = self._buckets.get(key)
        if b is None:
            return cap
        tokens, last, _ = b
        return min(cap, tokens + max(0.0, t - last) * self._rate)

    def _store(self, key, tokens, t):
        cap = self._cap(key)
        if tokens >= cap:
            self._buckets.pop(key, None)
            return
        seq = next(self._seq)
        self._buckets[key] = (tokens, t, seq)
        heapq.heappush(self._heap, (t + (cap - tokens) / self._rate, seq, key))

    def _sweep(self, t):
        heap = self._heap
        while heap and heap[0][0] <= t:
            full_at, seq, key = heapq.heappop(heap)
            b = self._buckets.get(key)
            if b is None or b[2] != seq:
                continue                          # stale entry
            if self._level(key, t) >= self._cap(key):
                del self._buckets[key]
            else:                                 # float rounding: look again just after t
                heapq.heappush(heap, (math.nextafter(t, math.inf), seq, key))

    def _take(self, demand, t):
        self._sweep(t)
        levels = {}
        for key, n in demand.items():
            levels[key] = self._level(key, t)
            if levels[key] < n:
                return False
        for key, n in demand.items():
            self._store(key, levels[key] - n, t)
        return True

    # -- public API --
    def acquire(self, key, tokens=1):
        _positive(tokens, "tokens")
        with self._lock:
            return self._take({key: tokens}, self._clock())

    def try_acquire_many(self, requests):
        demand = {}
        for key, n in requests:
            demand[key] = demand.get(key, 0) + _positive(n, "tokens")
        with self._lock:
            return self._take(demand, self._clock())

    def available(self, key):
        with self._lock:
            return float(self._level(key, self._clock()))

    def set_capacity(self, key, capacity):
        _positive(capacity, "capacity")
        with self._lock:
            t = self._clock()
            level = self._level(key, t)
            full = level >= self._cap(key)
            self._buckets.pop(key, None)
            self._caps[key] = capacity
            if not full:
                self._store(key, min(level, capacity), t)

    def __len__(self):
        with self._lock:
            return len(self._buckets)
