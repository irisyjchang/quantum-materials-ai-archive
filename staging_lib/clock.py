"""Timestamps used in database rows.

Timestamps are UTC ISO 8601 strings with microseconds. draft_runs.updated_at
must change on every hold, correction, and approval, because the stale-approval
check compares it (Requirement 13), so ``later_than`` never repeats a value.
"""

from datetime import datetime, timedelta, timezone


def now_iso():
    """Current UTC time as an ISO 8601 string, to the microsecond."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def later_than(previous):
    """A timestamp strictly after ``previous`` (an ISO string or None), normally the current time."""
    now = datetime.now(timezone.utc)
    if previous:
        try:
            earlier = datetime.fromisoformat(previous)
        except ValueError:
            earlier = None
        if earlier is not None and earlier.tzinfo is not None and now <= earlier:
            now = earlier + timedelta(microseconds=1)
    return now.isoformat(timespec="microseconds")
