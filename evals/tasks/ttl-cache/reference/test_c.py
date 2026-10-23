import unittest
from cache import TTLCache
class T(unittest.TestCase):
    def test(self): self.assertEqual(len(TTLCache(1,1)), 0)
