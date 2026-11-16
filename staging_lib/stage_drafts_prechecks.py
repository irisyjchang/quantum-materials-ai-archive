"""Version lookup and extraction gate for stage-drafts (Task 6.1, Requirements 2.3, 2.4, 21.3)."""

from staging_lib.errors import Rejection
from staging_lib.gate import check_gate


def require_cleared_version(connection, drive_file_id, file_hash):
    """Return the registered SourcePdf, or raise Rejection with the reason."""
    result = check_gate(connection, drive_file_id, file_hash)
    if result.source is None:
        raise Rejection(
            f"unknown PDF version: {drive_file_id} with file_hash {file_hash} is not registered. "
            "risk-assess must complete successfully for that exact version before drafts can be staged"
        )
    if not result.cleared:
        raise Rejection(f"extraction gate failed: {result.reason}; no drafts were staged")
    return result.source
