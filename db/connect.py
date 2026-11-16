"""Shared SQLite connection helper (Task 2.7).

The staging tool and the review app share one database file per environment,
so every connection enables foreign keys, uses WAL journal mode, and waits up
to 5000 ms for a lock instead of failing immediately.
"""

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def connect(path, *, read_only=False):
    """Open a SQLite connection with the MVP settings.

    With ``read_only=True`` the file is opened with ``mode=ro`` and must already
    exist; the journal mode is left as stored in the file.
    """
    if read_only:
        uri = f"file:{Path(path).resolve()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    else:
        connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    if not read_only and str(path) != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
    return connection
