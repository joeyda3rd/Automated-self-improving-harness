import re
from decimal import Decimal, ROUND_HALF_UP
UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
COMP = re.compile(r"(\d+(?:\.\d+)?)([dhms])")
def parse_duration(text):
    s = text.strip()
    if not s:
        raise ValueError("empty")
    pos, order, total, comps = 0, "dhms", Decimal(0), []
    while pos < len(s):
        m = COMP.match(s, pos)
        if not m:
            raise ValueError(text)
        comps.append(m)
        pos = m.end()
        if pos < len(s):
            if s[pos] == " ":
                pos += 1
                if pos >= len(s) or s[pos] == " ":
                    raise ValueError(text)
    last = -1
    for i, m in enumerate(comps):
        idx = order.index(m.group(2))
        if idx <= last:
            raise ValueError(text)
        last = idx
        if "." in m.group(1) and i != len(comps) - 1:
            raise ValueError(text)
        total += Decimal(m.group(1)) * UNITS[m.group(2)]
    return int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
def format_duration(seconds):
    if seconds < 0:
        raise ValueError(seconds)
    if seconds == 0:
        return "0s"
    out = ""
    for u, n in UNITS.items():
        q, seconds = divmod(seconds, n)
        if q:
            out += f"{q}{u}"
    return out
