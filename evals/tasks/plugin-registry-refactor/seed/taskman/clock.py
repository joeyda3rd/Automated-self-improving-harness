"""Today's date, overridable with TASKMAN_TODAY=YYYY-MM-DD (used by tests)."""
import datetime
import os


def today():
    forced = os.environ.get("TASKMAN_TODAY")
    if forced:
        return datetime.date.fromisoformat(forced)
    return datetime.date.today()
