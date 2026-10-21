"""Compute the next fire time of a 5-field cron expression."""
import calendar
import datetime as _dt
import re

_MONTHS = {n: i for i, n in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
_DAYS = {n: i for i, n in enumerate("SUN MON TUE WED THU FRI SAT".split())}
# (lo, hi, names)
_FIELDS = [(0, 59, None), (0, 23, None), (1, 31, None), (1, 12, _MONTHS), (0, 7, _DAYS)]
_ITEM = re.compile(r"^(\*|[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?)(?:/(\d+))?$")


def _value(tok, lo, hi, names):
    if tok.isdigit():
        v = int(tok)
    elif names is not None and tok.upper() in names:
        v = names[tok.upper()]
    else:
        raise ValueError(f"bad value {tok!r}")
    if not lo <= v <= hi:
        raise ValueError(f"value {v} out of range {lo}-{hi}")
    return v


def _parse_field(text, lo, hi, names):
    out = set()
    for item in text.split(","):
        m = _ITEM.match(item)
        if not m:
            raise ValueError(f"bad item {item!r}")
        base, step = m.group(1), m.group(2)
        step = 1 if step is None else int(step)
        if step < 1:
            raise ValueError("step must be >= 1")
        if base == "*":
            a, b = lo, hi
        elif "-" in base:
            sa, sb = base.split("-")
            a, b = _value(sa, lo, hi, names), _value(sb, lo, hi, names)
            if a > b:
                raise ValueError(f"reversed range {item!r}")
        else:
            a = _value(base, lo, hi, names)
            b = hi if m.group(2) is not None else a
        out.update(range(a, b + 1, step))
    return out


def parse(expr):
    if not isinstance(expr, str):
        raise ValueError("expression must be a string")
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("expected 5 fields")
    sets = [_parse_field(p, *f) for p, f in zip(parts, _FIELDS)]
    if 7 in sets[4]:
        sets[4].discard(7)
        sets[4].add(0)
    return sets, parts[2] != "*", parts[4] != "*"


def _satisfiable(doms, months, dom_r, dow_r):
    if dom_r and dow_r:
        return True
    if not dom_r:
        return True
    return any(d <= (29 if m == 2 else calendar.monthrange(2001, m)[1]) for m in months for d in doms)


def next_fire(expr, after):
    (mins, hours, doms, months, dows), dom_r, dow_r = parse(expr)
    if not _satisfiable(doms, months, dom_r, dow_r):
        raise ValueError("expression never fires")
    mins, hours = sorted(mins), sorted(hours)
    start = after.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
    day = start.date()
    first = True
    for _ in range(366 * 10):
        if day.month in months:
            dom_ok = day.day in doms
            dow_ok = (day.isoweekday() % 7) in dows
            if dom_r and dow_r:
                ok = dom_ok or dow_ok
            else:
                ok = (dom_ok or not dom_r) and (dow_ok or not dow_r)
            if ok:
                for h in hours:
                    if first and h < start.hour:
                        continue
                    for mi in mins:
                        if first and h == start.hour and mi < start.minute:
                            continue
                        return _dt.datetime(day.year, day.month, day.day, h, mi)
        first = False
        day += _dt.timedelta(days=1)
    raise ValueError("expression never fires")
