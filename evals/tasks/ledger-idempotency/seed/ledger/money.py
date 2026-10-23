"""Money helpers. All amounts inside the ledger are integers in cents."""
import re

from .errors import InvalidAmount

_MONEY = re.compile(r"(-)?([0-9]+)(?:\.([0-9]{1,2}))?")


def parse_money(text):
    """Parse ``"12.34"``, ``"-3.5"`` or ``"7"`` into cents.

    >>> parse_money("12.34")
    1234
    >>> parse_money("-0.5")
    -50
    """
    if not isinstance(text, str):
        raise InvalidAmount(f"not a string: {text!r}")
    m = _MONEY.fullmatch(text.strip())
    if not m:
        raise InvalidAmount(f"bad amount: {text!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int((frac or "0").ljust(2, "0"))
    return -cents if sign else cents


def format_money(cents):
    """Format cents as a fixed two-decimal string: ``1234 -> "12.34"``, ``-5 -> "-0.05"``."""
    if not isinstance(cents, int) or isinstance(cents, bool):
        raise TypeError(f"cents must be int, got {type(cents).__name__}")
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_column(cents, width=12):
    """Right-align a formatted amount in a column of ``width`` characters."""
    return format_money(cents).rjust(width)


def split_evenly(cents, parts):
    """Split ``cents`` into ``parts`` integer amounts that differ by at most one cent.

    The remainder goes to the first parts, so the result is deterministic.
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    base, extra = divmod(cents, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]
