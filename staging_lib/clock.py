"""Timestamps used in database rows."""

from datetime import datetime, timezone


def now_iso():
    """Current UTC time as an ISO 8601 string, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
