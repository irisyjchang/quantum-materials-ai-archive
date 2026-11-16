"""Restore a snapshot into a separate Test workspace (Task 23.2, Requirement 26.7).

Usage: python tools/restore.py <snapshot folder> --target <empty folder> [--reported-at <ISO time>]

The target is laid out like the repository so the review app and the restore
check can open it:

  <target>/test.sqlite
  <target>/review_workspace/test/
  <target>/retained_pdfs/test/
  <target>/restore_report.json

A snapshot of either environment is restored as Test. The target must be new
or empty, and must not be the repository or the folder the snapshot was taken
from, so a restore never overwrites test.sqlite, archive.sqlite, or their
folders. In the restored database only, source_pdfs.storage_path is rewritten
to the restored retained copies, so source links open the snapshot's PDF
versions and not the live files.

--reported-at is when the data loss was reported. When given, the elapsed
restore time is measured from it (Requirement 26.6); otherwise it is the
time this command took.

Then run: python tools/verify_restore.py <target>
"""

import argparse
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import env as environments  # noqa: E402
from db.connect import connect  # noqa: E402
from staging_lib.clock import now_iso  # noqa: E402
from tools.backup import MANIFEST_FORMAT, MANIFEST_NAME  # noqa: E402

REPORT_NAME = "restore_report.json"
RESTORED_ENV = "test"


class RestoreError(RuntimeError):
    """The restore was refused or failed; the message says why."""


def load_manifest(snapshot):
    path = Path(snapshot) / MANIFEST_NAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RestoreError(f"{snapshot} is not a snapshot folder: {MANIFEST_NAME} not found") from None
    except (OSError, json.JSONDecodeError) as error:
        raise RestoreError(f"{path} cannot be read: {error}") from None
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        raise RestoreError(f"{path} is not a format {MANIFEST_FORMAT} snapshot manifest")
    if manifest.get("env") not in environments.ENVIRONMENTS:
        raise RestoreError(f"{path} names an unknown environment {manifest.get('env')!r}")
    return manifest


def _same(first, second):
    return Path(first).resolve() == Path(second).resolve()


def check_target(target, manifest):
    """Raise RestoreError unless ``target`` is a new or empty folder separate from live data."""
    target = Path(target)
    if target.is_symlink():
        raise RestoreError(f"{target} is a symbolic link; restore into a real, empty folder")
    protected = [environments.PROJECT_ROOT]
    if manifest.get("source_root"):
        protected.append(manifest["source_root"])
    for folder in protected:
        if _same(target, folder):
            raise RestoreError(f"refusing to restore into {target}: it holds live data. Restore into a separate, "
                               "empty Test folder")
    if target.exists():
        if not target.is_dir():
            raise RestoreError(f"{target} is not a folder")
        if (target / "archive.sqlite").exists():
            raise RestoreError(f"refusing to restore over {target / 'archive.sqlite'}")
        if any(target.iterdir()):
            raise RestoreError(f"{target} is not empty; restore into a new or empty folder")


def restore(snapshot, target, reported_at=None):
    """Restore ``snapshot`` into ``target`` and return the restore report. Raises RestoreError."""
    started_clock, started_at = time.monotonic(), now_iso()
    snapshot = Path(snapshot)
    manifest = load_manifest(snapshot)
    source_env = manifest["env"]
    snapshot_database = snapshot / manifest.get("database", f"{source_env}.sqlite")
    if not snapshot_database.is_file():
        raise RestoreError(f"the snapshot database is missing: {snapshot_database}")
    reported = None
    if reported_at:
        try:
            reported = datetime.fromisoformat(reported_at)
        except ValueError:
            raise RestoreError(f"--reported-at {reported_at!r} is not an ISO 8601 time") from None
        if reported.tzinfo is None:
            raise RestoreError("--reported-at must include a time zone, for example 2026-11-16T09:00:00+00:00")
    check_target(target, manifest)

    environment = environments.resolve(RESTORED_ENV, root=Path(target).absolute())
    environment.database_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reader = connect(snapshot_database, read_only=True)
        try:
            writer = sqlite3.connect(environment.database_path)
            try:
                reader.backup(writer)
            finally:
                writer.close()
        finally:
            reader.close()

        workspace_source = snapshot / "review_workspace" / source_env
        if workspace_source.is_dir():
            shutil.copytree(workspace_source, environment.workspace_dir, symlinks=True)
        else:
            environment.workspace_dir.mkdir(parents=True)
        retained_source = snapshot / "retained_pdfs" / source_env
        if retained_source.is_dir():
            shutil.copytree(retained_source, environment.retained_dir)
        else:
            environment.retained_dir.mkdir(parents=True)

        rewritten = rewrite_storage_paths(environment)
    except (OSError, sqlite3.Error) as error:
        raise RestoreError(f"the restore into {target} failed: {error}. Delete {target} before trying again") from None

    finished_at = now_iso()
    if reported is not None:
        elapsed = (datetime.fromisoformat(finished_at) - reported).total_seconds()
        measured_from = "reported_at"
    else:
        elapsed = time.monotonic() - started_clock
        measured_from = "restore_start"
    report = {
        "snapshot": str(snapshot.resolve()),
        "snapshot_created_at": manifest.get("created_at"),
        "snapshot_env": source_env,
        "snapshot_complete": manifest.get("complete", False),
        "snapshot_problems": manifest.get("problems", []),
        "restored_env": RESTORED_ENV,
        "reported_at": reported_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": round(elapsed, 3),
        "elapsed_measured_from": measured_from,
        "storage_paths_rewritten": rewritten,
    }
    (Path(target) / REPORT_NAME).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def rewrite_storage_paths(environment):
    """Point every source_pdfs.storage_path in the restored database at the restored retained folder."""
    connection = connect(environment.database_path)
    try:
        rows = connection.execute(
            "SELECT pdf_id, storage_path FROM source_pdfs WHERE storage_path IS NOT NULL"
        ).fetchall()
        with connection:
            for pdf_id, storage_path in rows:
                restored = environment.retained_dir / Path(storage_path).name
                connection.execute("UPDATE source_pdfs SET storage_path = ? WHERE pdf_id = ?",
                                   (str(restored), pdf_id))
    finally:
        connection.close()
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Restore a snapshot into a separate Test workspace.")
    parser.add_argument("snapshot", help="snapshot folder written by tools/backup.py")
    parser.add_argument("--target", required=True, help="new or empty folder for the restored Test workspace")
    parser.add_argument("--reported-at", help="when the data loss was reported (ISO 8601 with time zone)")
    args = parser.parse_args(argv)
    try:
        report = restore(args.snapshot, args.target, args.reported_at)
    except RestoreError as error:
        print(f"restore refused: {error}", file=sys.stderr)
        return 1
    if not report["snapshot_complete"]:
        print("Warning: this snapshot was recorded as incomplete: " + "; ".join(report["snapshot_problems"]),
              file=sys.stderr)
    print(f"Restored {report['snapshot_env']} snapshot from {report['snapshot_created_at']} into {args.target} as Test "
          f"in {report['elapsed_seconds']} s. Next: python tools/verify_restore.py {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
