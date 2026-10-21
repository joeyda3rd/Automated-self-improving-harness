import unittest

from ratelimit import RateLimiter


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TestRateLimiter(unittest.TestCase):
    def test_refill_and_eviction(self):
        c = Clock()
        rl = RateLimiter(4, 0.5, clock=c)
        self.assertTrue(rl.acquire("a", 4))
        self.assertFalse(rl.acquire("a"))
        c.t = 2
        self.assertTrue(rl.acquire("a"))
        self.assertEqual(len(rl), 1)
        c.t = 10
        rl.acquire("b", 0.5)
        self.assertEqual(len(rl), 1)

    def test_many_is_atomic(self):
        rl = RateLimiter(2, 1, clock=Clock(), overrides={"x": 1})
        self.assertFalse(rl.try_acquire_many([("a", 1), ("x", 2)]))
        self.assertEqual(rl.available("a"), 2.0)
        self.assertTrue(rl.try_acquire_many([("a", 1), ("x", 1), ("a", 1)]))
        self.assertEqual(rl.available("a"), 0.0)


if __name__ == "__main__":
    unittest.main()
