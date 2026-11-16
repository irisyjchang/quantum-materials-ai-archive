"""Tests for risk-assess (Task 4.6).

Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 4.1, 5.1, 5.5, 8.5, 14.8, 24.1 to 24.3.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import query
from factories import PLACEHOLDER_DRIVE_ID
from staging_lib import status_store

ROOT = Path(__file__).resolve().parents[1]


def sources(database):
    return query(database, "SELECT pdf_id, drive_file_id, file_hash, storage_path, archive_filename FROM source_pdfs")


def status_row(database, pdf_id=None):
    sql = ("SELECT status, risk_decision, issues_json, clearance_by, clearance_at, clearance_note, reason"
           " FROM processing_status")
    rows = query(database, sql + (" WHERE pdf_id = ?" if pdf_id else ""), (pdf_id,) if pdf_id else ())
    return rows[0] if rows else None


def clear(database, pdf_id, by="Reviewer A", note="Ratio basis confirmed by the researcher"):
    query(database, "UPDATE processing_status SET status = 'cleared', clearance_by = ?, clearance_at = '2026-11-16T10:00:00+00:00', clearance_note = ? WHERE pdf_id = ?", (by, note, pdf_id))


ISSUE = [{"reason": "ratio basis unclear", "source_location": {"pdf_index": 1, "row": 2}}]


# First registration -----------------------------------------------------------

def test_first_call_registers_version_copy_and_status(workspace, capsys):
    database = workspace.database()
    assert workspace.risk_assess(workspace.risk_packet()) == 0
    rows = sources(database)
    assert len(rows) == 1
    pdf_id, drive_file_id, file_hash, storage_path, archive_filename = rows[0]
    assert (drive_file_id, file_hash, archive_filename) == (PLACEHOLDER_DRIVE_ID, workspace.pdf_hash, "log-1-901.pdf")
    retained = Path(storage_path)
    assert retained.is_absolute()
    assert retained == (workspace.root / "retained_pdfs" / "test" / f"{drive_file_id}-{file_hash}.pdf").resolve()
    assert hashlib.sha256(retained.read_bytes()).hexdigest() == workspace.pdf_hash
    assert status_row(database)[:2] == ("risk_assessed", "non_critical")
    assert "2 rows staged" in capsys.readouterr().out


def test_hash_mismatch_writes_nothing(workspace, capsys):
    database = workspace.database()
    assert workspace.risk_assess(workspace.risk_packet(file_hash="f" * 64)) == 1
    assert "do not match file_hash" in capsys.readouterr().err
    assert sources(database) == []
    assert status_row(database) is None
    assert not (workspace.root / "retained_pdfs").exists()


def test_malformed_packet_writes_nothing(workspace):
    database = workspace.database()
    packet = workspace.risk_packet()
    del packet["drive_file_id"]
    assert workspace.risk_assess(packet) == 1
    assert sources(database) == []
    assert not (workspace.root / "retained_pdfs").exists()


@pytest.mark.parametrize("decision, status", [
    ("non_critical", "risk_assessed"),
    ("critical", "held_pending_clearance"),
    ("uncertain", "held_pending_clearance"),
])
def test_decision_sets_status(workspace, decision, status):
    database = workspace.database()
    issues = [] if decision == "non_critical" else ISSUE
    assert workspace.risk_assess(workspace.risk_packet(decision, issues)) == 0
    row = status_row(database)
    assert row[0] == status
    if status == "held_pending_clearance":
        assert "ratio basis unclear" in row[6]
    else:
        assert row[6] is None


def test_issues_are_stored_or_null(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    assert status_row(database)[2] is None


def test_never_writes_drafts_or_growth_runs(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    assert query(database, "SELECT count(*) FROM draft_runs")[0][0] == 0
    assert query(database, "SELECT count(*) FROM growth_runs")[0][0] == 0


# Retries -------------------------------------------------------------------------

def test_identical_retry_adds_nothing(workspace, capsys):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    before = sources(database)
    capsys.readouterr()
    assert workspace.risk_assess(workspace.risk_packet()) == 0
    assert sources(database) == before
    assert "0 rows staged" in capsys.readouterr().out


def test_retry_after_clearance_keeps_clearance_and_status(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    pdf_id = sources(database)[0][0]
    clear(database, pdf_id)
    assert workspace.risk_assess(workspace.risk_packet("uncertain", ISSUE)) == 0
    status, decision, _, by, at, note, _ = status_row(database, pdf_id)
    assert (status, decision) == ("cleared", "uncertain")
    assert (by, at, note) == ("Reviewer A", "2026-11-16T10:00:00+00:00", "Ratio basis confirmed by the researcher")


def test_retry_on_extraction_complete_keeps_status(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    pdf_id = sources(database)[0][0]
    query(database, "UPDATE processing_status SET status = 'extraction_complete' WHERE pdf_id = ?", (pdf_id,))
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    status, decision, issues, *_ = status_row(database, pdf_id)
    assert (status, decision) == ("extraction_complete", "critical")
    assert "ratio basis unclear" in issues


def test_changed_decision_on_uncleared_version_follows_new_result(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    workspace.risk_assess(workspace.risk_packet("non_critical"))
    status, decision, issues, *_rest, reason = status_row(database)
    assert (status, decision, issues, reason) == ("risk_assessed", "non_critical", None, None)


def test_new_hash_for_same_drive_file_is_a_fresh_version(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    old_id = sources(database)[0][0]
    clear(database, old_id)
    replacement, new_hash = workspace.make_pdf("log-1-901.pdf", b"%PDF-1.4\n% replaced scan\n")
    assert workspace.risk_assess(workspace.risk_packet("critical", ISSUE, file_hash=new_hash),
                                 source_pdf=replacement) == 0
    rows = sources(database)
    assert len(rows) == 2
    new_id = next(row[0] for row in rows if row[2] == new_hash)
    assert new_id != old_id
    new_status = status_row(database, new_id)
    assert new_status[0] == "held_pending_clearance"
    assert new_status[3:6] == (None, None, None)
    assert status_row(database, old_id)[0] == "cleared"


# Retained copy on retry (1.9) ----------------------------------------------------

def test_missing_copy_is_recreated(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    storage_path = Path(sources(database)[0][3])
    storage_path.unlink()
    assert workspace.risk_assess(workspace.risk_packet()) == 0
    assert hashlib.sha256(storage_path.read_bytes()).hexdigest() == workspace.pdf_hash
    assert Path(sources(database)[0][3]) == storage_path


def test_missing_copy_is_not_recreated_from_wrong_bytes(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    storage_path = Path(sources(database)[0][3])
    storage_path.unlink()
    wrong, _ = workspace.make_pdf("other.pdf", b"%PDF-1.4\n% different bytes\n")
    assert workspace.risk_assess(workspace.risk_packet(), source_pdf=wrong) == 1
    assert not storage_path.exists()


def test_existing_copy_is_never_overwritten(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    storage_path = Path(sources(database)[0][3])
    storage_path.write_bytes(b"left as found")
    assert workspace.risk_assess(workspace.risk_packet()) == 0
    assert storage_path.read_bytes() == b"left as found"


# Recovery from technical failure (14.8) -----------------------------------------

def mark_failed(database, pdf_id):
    query(database, "UPDATE processing_status SET status = 'technical_failure', reason = 'disk full' WHERE pdf_id = ?", (pdf_id,))


def test_technical_failure_recovers_to_assessment_status(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    pdf_id = sources(database)[0][0]
    mark_failed(database, pdf_id)
    assert workspace.risk_assess(workspace.risk_packet("critical", ISSUE)) == 0
    status, *_rest, reason = status_row(database, pdf_id)
    assert status == "held_pending_clearance"
    assert "disk full" not in reason


def test_technical_failure_recovers_to_cleared(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    pdf_id = sources(database)[0][0]
    clear(database, pdf_id)
    mark_failed(database, pdf_id)
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    status, *_rest, reason = status_row(database, pdf_id)
    assert (status, reason) == ("cleared", None)


def test_technical_failure_recovers_to_extraction_complete_when_drafts_exist(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    pdf_id = sources(database)[0][0]
    query(database, "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json, review_status)"
                    " VALUES ('d1', ?, '[]', '{}', 'Pending review')", (pdf_id,))
    mark_failed(database, pdf_id)
    workspace.risk_assess(workspace.risk_packet())
    status, *_rest, reason = status_row(database, pdf_id)
    assert (status, reason) == ("extraction_complete", None)


# Atomicity (24.1, 24.2) -------------------------------------------------------------

def test_failure_inside_transaction_rolls_back_and_removes_copy(workspace, monkeypatch):
    database = workspace.database()

    def explode(*args, **kwargs):
        raise RuntimeError("simulated database error")

    monkeypatch.setattr(status_store, "record_assessment", explode)
    assert workspace.risk_assess(workspace.risk_packet()) == 1
    assert sources(database) == []
    retained = workspace.root / "retained_pdfs" / "test"
    assert not retained.exists() or list(retained.iterdir()) == []


def test_missing_database_is_not_created(workspace):
    database = workspace.root / "test.sqlite"
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 1
    assert not database.exists()


# Command line ---------------------------------------------------------------------

def test_missing_source_pdf_argument_exits_1(workspace):
    packet = workspace.write_packet(workspace.risk_packet())
    result = subprocess.run(
        [sys.executable, str(ROOT / "staging.py"), "risk-assess", str(packet), str(workspace.database())],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "--source-pdf" in result.stderr


def test_command_line_success(workspace):
    packet = workspace.write_packet(workspace.risk_packet())
    database = workspace.database()
    result = subprocess.run(
        [sys.executable, str(ROOT / "staging.py"), "risk-assess", str(packet),
         "--source-pdf", str(workspace.pdf), str(database)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "2 rows staged" in result.stdout
