"""Error types. Every error carries a short machine-readable `kind`."""


class TaskmanError(Exception):
    kind = "error"

    @property
    def message(self):
        return str(self.args[0]) if self.args else self.kind


class UsageError(TaskmanError):
    """Wrong number or shape of command arguments."""
    kind = "usage"


class ValidationError(TaskmanError):
    """An argument has the right shape but an invalid value."""
    kind = "validation"


class NotFoundError(TaskmanError):
    kind = "not_found"


class ConflictError(TaskmanError):
    """The command is valid but conflicts with the task's current state."""
    kind = "conflict"
