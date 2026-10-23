import unittest

from confload import ConfigError, InterpolationCycleError, load


class ConfloadTest(unittest.TestCase):
    def test_precedence(self):
        cfg = load({"a": "int", "m": "map"}, {"a": "1", "m": {"x": "1"}}, (), {"APP_A": "2", "APP_M__Y": "z"},
                   "APP", ["--a=3"])
        self.assertEqual(cfg.get("a"), 3)
        self.assertEqual(cfg.get("m"), {"x": "1", "y": "z"})
        self.assertEqual(cfg.explain("m.y"), "env:APP_M__Y")

    def test_errors(self):
        with self.assertRaises(ConfigError) as cm:
            load({"a": "int", "b": "bool"}, {"b": "x"}, (), {})
        self.assertEqual(cm.exception.problems, ["a: missing required value", 'b: expected bool, got "x" (from defaults)'])

    def test_cycle(self):
        with self.assertRaises(InterpolationCycleError):
            load({"a": "str"}, {"a": "${a}"}, (), {})


if __name__ == "__main__":
    unittest.main()
