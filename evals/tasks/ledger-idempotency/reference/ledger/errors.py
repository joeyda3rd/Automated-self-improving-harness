"""Exception hierarchy for the ledger service.

Every error raised on purpose by this package derives from ``LedgerError`` so
callers (the CLI, the HTTP adapter in the other repository) can catch one type.
"""


class LedgerError(Exception):
    """Base class for all ledger errors."""


class InvalidEvent(LedgerError):
    """The event is malformed: wrong fields, wrong types or out-of-range values."""


class UnknownAccount(LedgerError):
    """An event refers to an account that has not been opened."""


class AccountExists(LedgerError):
    """An ``open`` event names an account that is already open."""


class InsufficientFunds(LedgerError):
    """A transfer would take the source account below its overdraft limit."""


class InvalidAmount(LedgerError):
    """A money string could not be parsed."""


class IdempotencyConflict(LedgerError):
    """An idempotency key was reused with a different payload."""


class StaleEvent(LedgerError):
    """The event's seq is not newer than the last processed seq of its account."""


class SequenceConflict(LedgerError):
    """A different event already waits in the buffer with the same account and seq."""


class GapTooLarge(LedgerError):
    """Too many sequence numbers are missing before this event."""


class CorruptStore(LedgerError):
    """The event store cannot be replayed."""
