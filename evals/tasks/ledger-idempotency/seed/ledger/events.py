"""Event schema and validation.

An event is a JSON object (a Python dict once decoded). Two types exist:

``open``      ``{"key", "type": "open", "account", "seq", "limit"}``
``transfer``  ``{"key", "type": "transfer", "account", "seq", "to", "amount"}``

* ``key`` is the idempotency key chosen by the producer: a non-empty string.
* ``account`` is the account the event is sequenced on (for a transfer, the
  source account). Account names match ``[a-z][a-z0-9_]*``.
* ``seq`` is the producer's per-account sequence number, an int >= 1.
* ``limit`` is the overdraft limit in cents (int >= 0): the balance may go down
  to ``-limit`` but not below.
* ``amount`` is in cents, an int > 0; ``to`` must differ from ``account``.

No other fields are allowed and none may be missing.
"""
import re

from .errors import InvalidEvent

NAME = re.compile(r"[a-z][a-z0-9_]*")

FIELDS = {
    "open": {"key", "type", "account", "seq", "limit"},
    "transfer": {"key", "type", "account", "seq", "to", "amount"},
}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _check_name(event, field):
    value = event[field]
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise InvalidEvent(f"{field} must be an account name, got {value!r}")


def validate_event(event):
    """Return ``event`` unchanged if it is well formed, else raise ``InvalidEvent``."""
    if not isinstance(event, dict):
        raise InvalidEvent(f"event must be an object, got {type(event).__name__}")
    etype = event.get("type")
    if etype not in FIELDS:
        raise InvalidEvent(f"unknown event type {etype!r}")
    fields = set(event)
    if fields != FIELDS[etype]:
        missing = sorted(FIELDS[etype] - fields)
        extra = sorted(fields - FIELDS[etype])
        raise InvalidEvent(f"{etype} event fields: missing {missing}, unexpected {extra}")
    if not isinstance(event["key"], str) or not event["key"]:
        raise InvalidEvent("key must be a non-empty string")
    _check_name(event, "account")
    if not _is_int(event["seq"]) or event["seq"] < 1:
        raise InvalidEvent(f"seq must be an int >= 1, got {event['seq']!r}")
    if etype == "open":
        if not _is_int(event["limit"]) or event["limit"] < 0:
            raise InvalidEvent(f"limit must be an int >= 0, got {event['limit']!r}")
    else:
        _check_name(event, "to")
        if event["to"] == event["account"]:
            raise InvalidEvent("cannot transfer to the same account")
        if not _is_int(event["amount"]) or event["amount"] <= 0:
            raise InvalidEvent(f"amount must be an int > 0, got {event['amount']!r}")
    return event


def open_event(key, account, seq, limit=0):
    """Convenience constructor used by tests and the CLI."""
    return {"key": key, "type": "open", "account": account, "seq": seq, "limit": limit}


def transfer_event(key, account, seq, to, amount):
    """Convenience constructor used by tests and the CLI."""
    return {"key": key, "type": "transfer", "account": account, "seq": seq, "to": to, "amount": amount}


def describe(event):
    """One-line human readable description, used in logs and the CLI."""
    if event["type"] == "open":
        return f"{event['key']}: open {event['account']} (limit {event['limit']})"
    return f"{event['key']}: {event['account']} -> {event['to']} {event['amount']}"
