set -e
python3 - <<'PY'
from duration import parse_duration as p, format_duration as f
ok = {"1h30m": 5400, "90s": 90, "1.5h": 5400, "2d4h": 187200, "1h 1.5m": 3690, " 1h2m3s ": 3723,
      "0.5s": 1, "2.4999s": 2, "1d 1h 1m 1s": 90061, "0s": 0, "10m": 600, "1h2m": 3720, "0.25m": 15}
for text, want in ok.items():
    got = p(text)
    assert got == want and isinstance(got, int), (text, got, want)
bad = ["", "   ", "1m1h", "1h1h", "1H", "5", "h", "-5m", "+5m", "1.5h 30m", "1h  2m", "1x", "1.h", ".5h", "1h,2m", "1 h"]
for text in bad:
    try:
        p(text)
    except ValueError:
        continue
    raise AssertionError(f"accepted invalid {text!r}")
assert f(3723) == "1h2m3s" and f(90061) == "1d1h1m1s" and f(3600) == "1h" and f(0) == "0s" and f(86400) == "1d"
try:
    f(-1)
except ValueError:
    pass
else:
    raise AssertionError("format_duration(-1) must raise")
for s in ["1d", "2h5s", "59m59s", "3d23h59m59s"]:
    assert f(p(s)) == s, s
PY
python3 -m unittest -q 2>/dev/null
