import time
from collections import OrderedDict
class TTLCache:
    def __init__(self, capacity, ttl, clock=time.monotonic):
        if not isinstance(capacity, int) or capacity < 1 or ttl <= 0:
            raise ValueError("bad args")
        self.capacity, self.ttl, self.clock, self.d = capacity, ttl, clock, OrderedDict()
    def _alive(self, key):
        return key in self.d and self.clock() - self.d[key][1] < self.ttl
    def put(self, key, value):
        if key in self.d:
            self.d[key] = (value, self.clock()); self.d.move_to_end(key); return
        if len(self.d) >= self.capacity:
            for k in [k for k in self.d if not self._alive(k)]:
                del self.d[k]
            if len(self.d) >= self.capacity:
                self.d.popitem(last=False)
        self.d[key] = (value, self.clock())
    def get(self, key, default=None):
        if not self._alive(key):
            return default
        self.d.move_to_end(key); return self.d[key][0]
    def __contains__(self, key):
        return self._alive(key)
    def __len__(self):
        return sum(1 for k in self.d if self._alive(k))
