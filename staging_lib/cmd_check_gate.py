"""check-gate command (Task 5.2, Requirements 2.1, 2.2, 2.5).

Read-only. On exit 0 it prints two lines: ``cleared`` and the absolute path of
the retained copy, which the skill extracts from so extraction uses the exact
bytes that were assessed. Otherwise it exits 1 and prints the reason.
"""

import sqlite3
import sys
from pathlib import Path

from db.connect import connect
from staging_lib.gate import check_gate


def run(args):
    database = Path(args.database)
    if not database.is_file():
        print(f"check-gate: database not found: {database}", file=sys.stderr)
        return 1
    drive_file_id = args.drive_file_id.strip()
    file_hash = args.file_hash.strip().lower()
    try:
        connection = connect(database, read_only=True)
        try:
            result = check_gate(connection, drive_file_id, file_hash)
        finally:
            connection.close()
    except sqlite3.Error as error:
        print(f"check-gate: {error}", file=sys.stderr)
        return 1
    if not result.cleared:
        print(f"check-gate: not cleared: {result.reason}", file=sys.stderr)
        return 1
    storage_path = result.source.storage_path
    if not storage_path or not Path(storage_path).is_file():
        print(f"check-gate: cleared, but the retained copy is missing ({storage_path}); "
              "rerun risk-assess with --source-pdf to restore it", file=sys.stderr)
        return 1
    print("cleared")
    print(storage_path)
    return 0
