import unittest
from fizzbuzz import fb
class T(unittest.TestCase):
    def test(self): self.assertEqual(fb(3)[-1],"Fizz")
