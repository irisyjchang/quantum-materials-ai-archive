"""Take a consistent snapshot of an environment (Task 23.1, Requirements 26.1 to 26.4).

Usage: python tools/backup.py snapshot --env <test|archive> [--dest <folder>] [--reason <label>] [--root <folder>]

The snapshot is a folder inside the destination:

  <name>/manifest.json               what was copied, row counts, and any problems
  <name>/<env>.sqlite                SQLite backup-API copy of the live database
  <name>/review_workspace/<env>/     corrections and the action log
  <name>/retained_pdfs/<env>/        every retained PDF version named in source_pdfs.storage_path,
                                     checked against file_hash

The destination is --dest, else ``backup_folder`` in config.json. The lab has
not confirmed a backup folder yet, so with neither the command refuses. The
folder name uses ``backup_name_pattern`` from config.json when the lab sets it
(placeholders {env}, {timestamp}, {reason}); otherwise
growth-log-<env>-<UTC timestamp>-<reason>.

The last successful backup is recorded in backups/status-<env>.json. A failed
backup exits 1, records the failure, and leaves the last-success value as it
was. A snapshot whose retained PDFs are missing or changed is kept, with
``complete: false`` in its manifest, but counts as a failure.

Use --reason pre-migration before any database migration (Requirement 26.1).
The command only reads the live database, workspace, and retained PDFs.
"""

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import backup_status  # noqa: E402
from common.config import ConfigError, load_config  # noqa: E402
from db import env as environments  # noqa: E402
from db.connect import connect  # noqa: E402
from staging_lib.clock import now_iso  # noqa: E402
from staging_lib.source_pdf import sha256_file  # noqa: E402

MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = 1
TABLES = ("source_pdfs", "draft_runs", "growth_runs", "run_revisions", "processing_status")
NO_FOLDER_MESSAGE = ("no backup destination: the lab has not confirmed a backup folder yet. Set backup_folder in "
                     "config.json once it is confirmed, or pass --dest <folder> (Requirement 26.4)")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BackupError(RuntimeError):
    """The backup did not complete; the message says why."""


def snapshot_name(pattern, env_name, reason, moment):
    timestamp = moment.strftime("%Y%m%dT%H%M%SZ")
    if pattern is None:
        name = f"growth-log-{env_name}-{timestamp}-{reason}"
    else:
        try:
            name = pattern.format(env=env_name, timestamp=timestamp, reason=reason)
        except (KeyError, IndexError, ValueError) as error:
            raise BackupError(f"backup_name_pattern {pattern!r} is not usable: {error}; "
                              "allowed placeholders are {env}, {timestamp}, {reason}") from None
    if not _SAFE_COMPONENT.match(name):
        raise BackupError(f"snapshot name {name!r} must be one folder name using letters, digits, '.', '_' or '-'")
    return name


def _unique_folder(destination, name):
    candidate, number = destination / name, 2
    while candidate.exists() or (destination / f".{candidate.name}.partial").exists():
        candidate, number = destination / f"{name}-{number}", number + 1
    return candidate


def copy_database(source, target):
    """Copy ``source`` to ``target`` with SQLite's backup API; the copy is a single self-contained file."""
    reader = connect(source, read_only=True)
    try:
        writer = sqlite3.connect(target)
        try:
            reader.backup(writer)
            writer.execute("PRAGMA journal_mode = DELETE")
            result = writer.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise BackupError(f"the snapshot of {source} failed SQLite's integrity check: {result}")
        finally:
            writer.close()
    finally:
        reader.close()


def database_summary(path):
    """Row counts and the newest approval in a database file (read-only)."""
    connection = connect(path, read_only=True)
    try:
        counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLES}
        newest = connection.execute("SELECT max(approved_at) FROM run_revisions").fetchone()[0]
        pdfs = connection.execute(
            "SELECT pdf_id, archive_filename, file_hash, storage_path FROM source_pdfs ORDER BY pdf_id"
        ).fetchall()
    finally:
        connection.close()
    return counts, newest, pdfs


def copy_retained(pdfs, target_dir, env_name):
    """Copy each recorded retained PDF version, verifying its SHA-256. Returns (entries, problems)."""
    entries, problems, used = [], [], set()
    target_dir.mkdir(parents=True, exist_ok=True)
    for pdf_id, filename, file_hash, storage_path in pdfs:
        if not storage_path:
            problems.append(f"{pdf_id} ({filename}) has no retained copy recorded")
            continue
        source = Path(storage_path)
        if not source.is_file():
            problems.append(f"{pdf_id} ({filename}) retained copy is missing: {source}")
            continue
        if sha256_file(source) != (file_hash or "").lower():
            problems.append(f"{pdf_id} ({filename}) retained copy no longer matches file_hash: {source}")
            continue
        if source.name in used:
            problems.append(f"{pdf_id} ({filename}) retained copy name {source.name} is used by another PDF")
            continue
        used.add(source.name)
        destination = target_dir / source.name
        shutil.copy2(source, destination)
        if sha256_file(destination) != file_hash.lower():
            problems.append(f"{pdf_id} ({filename}) copy in the snapshot does not match file_hash")
            continue
        entries.append({
            "pdf_id": pdf_id,
            "archive_filename": filename,
            "file_hash": file_hash,
            "original_storage_path": str(source),
            "file": f"retained_pdfs/{env_name}/{source.name}",
        })
    return entries, problems


def take_snapshot(environment, destination, reason, name_pattern=None, moment=None):
    """Write a snapshot folder into ``destination`` and return (folder, manifest). Raises BackupError.

    A partial folder is removed when copying fails. When retained PDFs are missing or
    changed the folder is kept with ``complete: false`` and BackupError is raised.
    """
    moment = moment or datetime.now(timezone.utc)
    destination = Path(destination)
    if not destination.is_dir():
        raise BackupError(f"backup folder not found: {destination}")
    if not environment.database_path.is_file():
        raise BackupError(f"{environment.label} database not found at {environment.database_path}")
    final = _unique_folder(destination, snapshot_name(name_pattern, environment.name, reason, moment))
    partial = destination / f".{final.name}.partial"
    try:
        partial.mkdir()
        database_copy = partial / environment.database_path.name
        copy_database(environment.database_path, database_copy)
        counts, newest, pdfs = database_summary(database_copy)
        workspace_copy = partial / "review_workspace" / environment.name
        if environment.workspace_dir.is_dir():
            shutil.copytree(environment.workspace_dir, workspace_copy, symlinks=True)
        else:
            workspace_copy.mkdir(parents=True)
        retained, problems = copy_retained(pdfs, partial / "retained_pdfs" / environment.name, environment.name)
        manifest = {
            "format": MANIFEST_FORMAT,
            "env": environment.name,
            "created_at": now_iso(),
            "reason": reason,
            "source_root": str(environment.database_path.parent),
            "source_database": str(environment.database_path),
            "database": environment.database_path.name,
            "tables": counts,
            "newest_approval_at": newest,
            "retained_pdfs": retained,
            "complete": not problems,
            "problems": problems,
        }
        (partial / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        partial.rename(final)
    except (OSError, sqlite3.Error, BackupError) as error:
        shutil.rmtree(partial, ignore_errors=True)
        if isinstance(error, BackupError):
            raise
        raise BackupError(f"the snapshot could not be written: {error}") from None
    if problems:
        raise BackupError(f"snapshot {final} is incomplete: " + "; ".join(problems))
    return final, manifest


def run_snapshot(env_name, dest=None, reason="manual", root=environments.PROJECT_ROOT, config_path=None):
    """Take a snapshot and record the outcome. Returns (exit code, message)."""
    try:
        environment = environments.resolve(env_name, root=root)
    except ValueError as error:
        return 1, str(error)
    if not _SAFE_COMPONENT.match(reason or ""):
        return 1, f"--reason {reason!r} must use letters, digits, '.', '_' or '-' (for example pre-migration)"
    try:
        config = load_config(config_path)
    except ConfigError as error:
        return 1, f"config problem: {error}"
    destination = dest or config.backup_folder
    if not destination:
        return 1, NO_FOLDER_MESSAGE
    try:
        folder, manifest = take_snapshot(environment, destination, reason, config.backup_name_pattern)
    except BackupError as error:
        backup_status.record_failure(root, environment.name, {
            "at": now_iso(), "error": str(error), "reason": reason, "destination": str(destination),
        })
        return 1, f"backup failed: {error}. The last successful backup was not changed."
    backup_status.record_success(root, environment.name, {
        "at": manifest["created_at"], "snapshot": str(folder), "destination": str(destination),
        "reason": reason, "tables": manifest["tables"],
    })
    return 0, (f"Snapshot of {environment.label} written to {folder} "
               f"({manifest['tables']['growth_runs']} approved runs, "
               f"{len(manifest['retained_pdfs'])} retained PDF versions).")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Back up the Test or Archive environment.")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="write a consistent snapshot")
    snapshot.add_argument("--env", required=True, help="test or archive")
    snapshot.add_argument("--dest", help="backup folder (default: backup_folder in config.json)")
    snapshot.add_argument("--reason", default="manual", help="label such as daily or pre-migration")
    snapshot.add_argument("--root", default=str(environments.PROJECT_ROOT),
                          help="folder that holds the environment databases (default: the repository)")
    args = parser.parse_args(argv)
    code, message = run_snapshot(args.env, args.dest, args.reason, args.root)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
