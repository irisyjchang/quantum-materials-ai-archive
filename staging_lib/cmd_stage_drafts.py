"""stage-drafts command (Task 6.4).

Order: validate the extraction packet, apply the reserved-PDF guard, then in one
transaction look up the registered version, enforce the extraction gate, insert
new drafts as Pending review, and set processing_status to extraction_complete.
Rejections (unknown version, failed gate, conflict) write nothing. An unexpected
processing error rolls back and records a technical failure for the version.
"""

import sys
from pathlib import Path

from common.config import ConfigError, load_config
from db.connect import connect
from staging_lib import draft_store, registry, reserved_guard
from staging_lib.errors import Rejection
from staging_lib.failure_record import record_technical_failure
from staging_lib.packet import PacketError, load_packet
from staging_lib.stage_drafts_prechecks import require_cleared_version


def fail(message):
    print(f"stage-drafts: {message}", file=sys.stderr)
    return 1


def run(args):
    try:
        packet = load_packet(args.packet, "extraction")
    except PacketError as error:
        return fail(error)
    drive_file_id = packet["drive_file_id"].strip()
    file_hash = packet["file_hash"].strip().lower()

    try:
        checklist_path = load_config().checklist_path
        guard = reserved_guard.check(args.database, drive_file_id, args.acceptance_run, checklist_path)
    except (ConfigError, reserved_guard.ReservedListError) as error:
        return fail(error)
    if guard.notice:
        print(guard.notice, file=sys.stderr)
    if guard.error:
        return fail(guard.error)

    database = Path(args.database)
    if not database.is_file():
        return fail(f"database not found: {database}")

    connection = connect(database)
    connection.isolation_level = None
    registered_pdf_id = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        found = registry.find_version(connection, drive_file_id, file_hash)
        registered_pdf_id = found.pdf_id if found else None
        source = require_cleared_version(connection, drive_file_id, file_hash)
        inserted = draft_store.stage_runs(connection, source.pdf_id, packet["runs"])
        draft_store.mark_extraction_complete(connection, source.pdf_id)
        connection.execute("COMMIT")
    except Rejection as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()
        return fail(error)
    except Exception as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()
        recorded = registered_pdf_id is not None and record_technical_failure(
            database, registered_pdf_id, f"stage-drafts failed: {error}")
        outcome = ("no drafts were staged; recorded as a technical failure, retry the same command"
                   if recorded else "no drafts were staged")
        return fail(f"{error}; {outcome}")
    connection.close()

    skipped = len(packet["runs"]) - inserted
    note = f" ({skipped} already staged, unchanged)" if skipped else ""
    print(f"{inserted} rows staged as Pending review for {source.archive_filename} ({drive_file_id}){note}.")
    return 0
