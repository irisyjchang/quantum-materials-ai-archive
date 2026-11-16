"""Check a restored Test workspace (Task 23.3, Requirements 26.5 to 26.7).

Usage: python tools/verify_restore.py <restored folder>

Read-only checks against <folder>/test.sqlite:

- the database passes SQLite's integrity check and has the MVP tables
- it holds approved runs, and the search query builder finds every one of them,
  with no criteria and by its own month, researcher name, both together, and JC number
- every approved run has its run_revisions history (versions 1..N, each with an
  approver and approval time)
- every source_pdfs.storage_path is inside the restored folder, exists, and has a
  SHA-256 equal to file_hash, and every approved run's PDF has a retained copy

It then reports the elapsed restore time (from restore_report.json) and the age
of the newest restored approval, for comparison with the lab's recovery
targets. Those targets are pending lab confirmation, so they are shown as
proposals and are not pass or fail checks.

Exits 0 when every check passes and 1 otherwise.
"""

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import env as environments  # noqa: E402
from db.connect import connect  # noqa: E402
from review_app.search.query import SearchCriteria, search  # noqa: E402
from staging_lib.source_pdf import sha256_file  # noqa: E402
from tools.restore import REPORT_NAME, RESTORED_ENV  # noqa: E402

REQUIRED_TABLES = {"source_pdfs", "draft_runs", "growth_runs", "run_revisions", "processing_status"}
PROPOSED_TARGETS = ("Proposed recovery targets (pending lab confirmation): lose at most one day of approvals and "
                    "corrections; restore searchable records, review history, and source PDF links within one "
                    "working day of the data-loss report.")


@dataclass
class Check:
    name: str
    ok: bool
    details: list


@dataclass
class Verification:
    checks: list
    elapsed_seconds: object
    elapsed_measured_from: object
    newest_approval_at: object
    newest_approval_age_seconds: object
    snapshot_created_at: object

    @property
    def ok(self):
        return all(check.ok for check in self.checks)


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False


def check_database(connection):
    problems = []
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        problems.append(f"integrity check: {result}")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = REQUIRED_TABLES - tables
    if missing:
        problems.append("missing tables: " + ", ".join(sorted(missing)))
    return Check("Database opens and has the MVP schema", not problems, problems)


def _criteria_for(run):
    name, growth_date, jc = run["researcher_name"], run["growth_date"], run["jc_number"]
    month = growth_date[:7] if growth_date else ""
    cases = [("no criteria", SearchCriteria())]
    if month:
        cases.append((f"month {month}", SearchCriteria(month=month)))
    if name:
        cases.append((f"name {name!r}", SearchCriteria(name=name)))
    if month and name:
        cases.append((f"name {name!r} and month {month}", SearchCriteria(name=name, month=month)))
    if jc:
        cases.append((f"JC {jc!r}", SearchCriteria(jc=jc)))
    return cases


def check_search(connection):
    runs = [dict(zip(("run_id", "researcher_name", "growth_date", "jc_number"), row)) for row in connection.execute(
        "SELECT run_id, researcher_name, growth_date, jc_number FROM growth_runs ORDER BY run_id")]
    if not runs:
        return Check("Approved runs are searchable", False,
                     ["no approved runs were restored; the drill needs a snapshot with approved runs"])
    problems = []
    all_ids = {row["run_id"] for row in search(connection, SearchCriteria())}
    if all_ids != {run["run_id"] for run in runs}:
        problems.append("search with no criteria does not return exactly the approved runs")
    for run in runs:
        for label, criteria in _criteria_for(run)[1:]:
            if run["run_id"] not in {row["run_id"] for row in search(connection, criteria)}:
                problems.append(f"{run['run_id']} is not found by {label}")
    details = problems or [f"{len(runs)} approved runs found by their month, name, and JC number"]
    return Check("Approved runs are searchable", not problems, details)


def check_revisions(connection):
    problems, total = [], 0
    runs = [row[0] for row in connection.execute("SELECT run_id FROM growth_runs ORDER BY run_id")]
    for run_id in runs:
        rows = connection.execute(
            "SELECT version, approved_by, approved_at, approved_values_json FROM run_revisions"
            " WHERE run_id = ? ORDER BY version", (run_id,)).fetchall()
        total += len(rows)
        if not rows:
            problems.append(f"{run_id} has no revision history")
            continue
        if [row[0] for row in rows] != list(range(1, len(rows) + 1)):
            problems.append(f"{run_id} revision versions are not 1 to {len(rows)}")
        for version, approved_by, approved_at, values in rows:
            if not (approved_by or "").strip() or not (approved_at or "").strip():
                problems.append(f"{run_id} version {version} has no approver or approval time")
            try:
                json.loads(values)
            except (TypeError, json.JSONDecodeError):
                problems.append(f"{run_id} version {version} approved values are not valid JSON")
    details = problems or [f"{total} revisions for {len(runs)} approved runs"]
    return Check("Review history is present", not problems, details)


def check_source_pdfs(connection, root):
    problems, checked = [], 0
    approved_pdfs = {row[0] for row in connection.execute("SELECT DISTINCT pdf_id FROM growth_runs")}
    for pdf_id, filename, file_hash, storage_path in connection.execute(
            "SELECT pdf_id, archive_filename, file_hash, storage_path FROM source_pdfs ORDER BY pdf_id"):
        label = f"{pdf_id} ({filename})"
        if not storage_path:
            if pdf_id in approved_pdfs:
                problems.append(f"{label} has approved runs but no retained copy recorded")
            continue
        checked += 1
        path = Path(storage_path)
        if not _inside(path, root):
            problems.append(f"{label} storage_path points outside the restored folder: {path}")
        elif not path.is_file():
            problems.append(f"{label} retained copy is missing: {path}")
        elif sha256_file(path) != (file_hash or "").lower():
            problems.append(f"{label} retained copy SHA-256 does not equal file_hash: {path}")
    details = problems or [f"{checked} retained PDF versions match their file_hash"]
    return Check("Source PDF links open the exact versions", not problems, details)


def _parse_time(value):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else None


def verify(root, now=None):
    """Run every check against the restored folder ``root``. Returns a Verification."""
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    environment = environments.resolve(RESTORED_ENV, root=root)
    report_path = root / REPORT_NAME
    report = {}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
    if not environment.database_path.is_file():
        return Verification([Check("Database opens and has the MVP schema", False,
                                   [f"restored database not found: {environment.database_path}"])],
                            None, None, None, None, None)
    try:
        connection = connect(environment.database_path, read_only=True)
    except sqlite3.Error as error:
        return Verification([Check("Database opens and has the MVP schema", False, [str(error)])],
                            None, None, None, None, None)
    try:
        checks = [check_database(connection)]
        if checks[0].ok:
            checks += [check_search(connection), check_revisions(connection), check_source_pdfs(connection, root)]
            newest = connection.execute("SELECT max(approved_at) FROM run_revisions").fetchone()[0]
        else:
            newest = None
    except sqlite3.Error as error:
        checks, newest = [Check("Database opens and has the MVP schema", False, [str(error)])], None
    finally:
        connection.close()
    newest_time = _parse_time(newest)
    age = (now - newest_time).total_seconds() if newest_time else None
    if not report:
        checks.append(Check("Restore report is present", False,
                            [f"{report_path} not found; restore with tools/restore.py to record the elapsed time"]))
    return Verification(checks, report.get("elapsed_seconds"), report.get("elapsed_measured_from"), newest, age,
                        report.get("snapshot_created_at"))


def _duration(seconds):
    if seconds is None:
        return "unknown"
    hours, remainder = divmod(int(round(seconds)), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours} h {minutes} min {secs} s"


def render(verification):
    lines = []
    for check in verification.checks:
        lines.append(f"{'PASS' if check.ok else 'FAIL'}  {check.name}")
        lines.extend(f"      {detail}" for detail in check.details)
    measured = {"reported_at": "since the data-loss report",
                "restore_start": "restore command only; pass --reported-at to restore.py to measure from the report"}
    lines.append(f"Elapsed restore time: {_duration(verification.elapsed_seconds)} "
                 f"({measured.get(verification.elapsed_measured_from, 'not recorded')})")
    lines.append(f"Snapshot taken at: {verification.snapshot_created_at or 'unknown'}")
    lines.append(f"Newest restored approval: {verification.newest_approval_at or 'none'} "
                 f"(age {_duration(verification.newest_approval_age_seconds)})")
    lines.append(PROPOSED_TARGETS)
    lines.append("Restore check passed." if verification.ok else "Restore check FAILED.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a restored Test workspace.")
    parser.add_argument("root", help="restored folder written by tools/restore.py")
    args = parser.parse_args(argv)
    verification = verify(args.root)
    print(render(verification))
    return 0 if verification.ok else 1


if __name__ == "__main__":
    sys.exit(main())
