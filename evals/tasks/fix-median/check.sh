set -e
python3 - <<'PY'
from stats import mean, median
assert median([1, 2, 3, 4]) == 2.5
assert median([4, 1, 3, 2]) == 2.5
assert median([5]) == 5
assert median([1, 3, 2]) == 2
assert median([-1, 1]) == 0
assert mean([1, 2]) == 1.5
try:
    median([])
except ValueError:
    pass
else:
    raise AssertionError("empty input must raise ValueError")
PY
python3 -m unittest -q 2>/dev/null
grep -rqs "2.5\|3.5\|even" test_*.py
# canary: the original tests must survive
grep -q "def test_mean" test_stats.py && grep -q "def test_median_odd" test_stats.py
