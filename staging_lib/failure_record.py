"""Technical-failure recording (Task 6.3, Requirements 14.7, 21.6, 23.2, 24.2).

Called only after a command's own transaction has rolled back because of an
unexpected processing error (for example a file copy or database error) on a
version that is already registered. Validation failures, conflicts, gate
rejections, and unregistered versions never reach this function.

The record is written in its own transaction and touches only
processing_status, never draft_runs, growth_runs, or run_revisions.
"""

import sys

from db.connect import connect
from staging_lib.clock import now_iso


def record_technical_failure(database, pdf_id, reason):
    """Set status = technical_failure with a reason. Returns True when recorded."""
    reason = str(reason).strip() or "unexpected processing error"
    try:
        connection = connect(database)
        connection.isolation_level = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE processing_status SET status = 'technical_failure', reason = ?, updated_at = ?"
                " WHERE pdf_id = ?",
                (reason, now_iso(), pdf_id),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
    except Exception as error:  # a failed failure record must not hide the original error
        print(f"could not record the technical failure: {error}", file=sys.stderr)
        return False
