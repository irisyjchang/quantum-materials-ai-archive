"""risk-assess command (Task 4.5).

Order: validate the packet, apply the reserved-PDF guard, verify the source
PDF's SHA-256 against file_hash, then in one transaction register the version
(with its retained copy) and record its assessment result. Any failure rolls
back, removes a retained copy created by this call, and exits 1. It never
writes draft_runs or growth_runs.
"""

import sys
from pathlib import Path

from common.config import ConfigError, load_config
from db.connect import connect
from db.env import retained_dir_for_database
from staging_lib import registry, retain, reserved_guard, status_store
from staging_lib.failure_record import record_technical_failure
from staging_lib.packet import PacketError, load_packet
from staging_lib.source_pdf import verify_file_hash


def fail(message):
    print(f"risk-assess: {message}", file=sys.stderr)
    return 1


def run(args):
    try:
        packet = load_packet(args.packet, "risk")
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

    error = verify_file_hash(args.source_pdf, file_hash)
    if error:
        return fail(f"{error}; nothing was recorded")

    database = Path(args.database)
    if not database.is_file():
        return fail(f"database not found: {database}; create it with python db/init_db.py {database}")

    connection = connect(database)
    connection.isolation_level = None  # explicit transaction control
    created_copy = None
    registered_pdf_id = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = 0
        source = registry.find_version(connection, drive_file_id, file_hash)
        registered_pdf_id = source.pdf_id if source else None
        if source is None:
            destination = retained_dir_for_database(database) / retain.retained_name(drive_file_id, file_hash)
            if retain.copy_verified(args.source_pdf, destination, file_hash):
                created_copy = destination
            source = registry.register(connection, drive_file_id, file_hash,
                                       Path(args.source_pdf).name, destination.resolve())
            rows += 1
        else:
            storage = source.storage_path
            if storage is None:
                storage = retained_dir_for_database(database) / retain.retained_name(drive_file_id, file_hash)
                registry.set_storage_path(connection, source.pdf_id, Path(storage).resolve())
                rows += 1
            if not Path(storage).exists():
                # Requirement 1.9: recreate a missing retained copy; the hash was verified above.
                if retain.copy_verified(args.source_pdf, storage, file_hash):
                    created_copy = Path(storage)
        result = status_store.record_assessment(
            connection, source.pdf_id, file_hash, packet["decision"], packet["issues"]
        )
        rows += int(result.changed)
        connection.execute("COMMIT")
    except Exception as error:  # roll back on any failure, then report it
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()
        retain.remove_created(created_copy)
        # Requirement 14.7: an unexpected error on an already-registered version is recorded.
        recorded = registered_pdf_id is not None and record_technical_failure(
            database, registered_pdf_id, f"risk-assess failed: {error}")
        outcome = "recorded as a technical failure; retry the same command" if recorded else "nothing was recorded"
        return fail(f"{error}; {outcome}")
    connection.close()

    print(f"{rows} rows staged: {source.archive_filename} ({drive_file_id}) is {result.status} "
          f"with assessment result {result.risk_decision}.")
    return 0
