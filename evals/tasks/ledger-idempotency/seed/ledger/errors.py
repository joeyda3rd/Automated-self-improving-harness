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
