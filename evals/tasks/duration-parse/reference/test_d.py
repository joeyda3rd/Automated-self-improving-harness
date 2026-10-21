import unittest
from duration import parse_duration
class T(unittest.TestCase):
    def test(self): self.assertEqual(parse_duration("1h"), 3600)
