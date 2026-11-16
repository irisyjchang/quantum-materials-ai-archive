"""Schema tests for the Local Growth Log MVP (Task 1.2)."""

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

EXPECTED_COLUMNS = {
    "source_pdfs": {
        "pdf_id", "archive_filename", "drive_file_id", "file_hash", "storage_path",
    },
    "draft_runs": {
        "draft_id", "pdf_id", "source_locations_json", "original_json",
        "review_status", "hold_reason", "updated_at",
    },
    "growth_runs": {
        "run_id", "pdf_id", "researcher_name", "growth_date", "date_precision",
        "jc_number", "growth_process", "composition_json",
        "source_locations_json", "details_json",
    },
    "run_revisions": {
        "revision_id", "run_id", "version", "approved_values_json", "changes_json",
        "edited_by", "edited_at", "approved_by", "approved_at",
    },
    "processing_status": {
        "pdf_id", "file_hash", "status", "risk_decision", "issues_json",
        "clearance_by", "clearance_at", "clearance_note", "reason", "updated_at",
    },
}


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def add_pdf(db, pdf_id="pdf-1", drive_file_id="drive-1", file_hash="hash-1"):
    db.execute(
        "INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash, storage_path)"
        " VALUES (?, ?, ?, ?, ?)",
        (pdf_id, "log-1-001.pdf", drive_file_id, file_hash, "/tmp/retained.pdf"),
    )


def add_draft(db, review_status, hold_reason, draft_id="draft-1"):
    db.execute(
        "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json,"
        " review_status, hold_reason, updated_at) VALUES (?, 'pdf-1', '[]', '{}', ?, ?, 'now')",
        (draft_id, review_status, hold_reason),
    )


def test_exactly_the_five_mvp_tables_exist(db):
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert tables == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize("table", sorted(EXPECTED_COLUMNS))
def test_table_has_expected_columns(db, table):
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    assert columns == EXPECTED_COLUMNS[table]


def test_no_pilot_objects(db):
    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
    assert "growth_logs" not in names
    assert "growth_log_index" not in names


def test_source_pdf_requires_drive_file_id(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO source_pdfs (pdf_id, archive_filename, file_hash) VALUES ('p', 'f', 'h')"
        )


def test_duplicate_version_is_rejected(db):
    add_pdf(db)
    with pytest.raises(sqlite3.IntegrityError):
        add_pdf(db, pdf_id="pdf-2")


def test_same_drive_file_with_new_hash_is_a_new_version(db):
    add_pdf(db)
    add_pdf(db, pdf_id="pdf-2", file_hash="hash-2")
    count = db.execute("SELECT count(*) FROM source_pdfs WHERE drive_file_id = 'drive-1'")
    assert count.fetchone()[0] == 2


@pytest.mark.parametrize("hold_reason", [None, "", "   "])
def test_held_draft_needs_a_hold_reason(db, hold_reason):
    add_pdf(db)
    with pytest.raises(sqlite3.IntegrityError):
        add_draft(db, "Held", hold_reason)


def test_held_draft_with_reason_is_accepted(db):
    add_pdf(db)
    add_draft(db, "Held", "Ratio basis unclear, page 1 row 2")


def test_review_status_is_limited(db):
    add_pdf(db)
    with pytest.raises(sqlite3.IntegrityError):
        add_draft(db, "Rejected", None)


def test_draft_requires_a_registered_pdf(db):
    with pytest.raises(sqlite3.IntegrityError):
        add_draft(db, "Pending review", None)


def test_processing_status_values_are_limited(db):
    add_pdf(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO processing_status (pdf_id, file_hash, status, updated_at)"
            " VALUES ('pdf-1', 'hash-1', 'done', 'now')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO processing_status (pdf_id, file_hash, status, risk_decision, updated_at)"
            " VALUES ('pdf-1', 'hash-1', 'risk_assessed', 'maybe', 'now')"
        )


def test_processing_status_has_one_row_per_pdf(db):
    add_pdf(db)
    insert = (
        "INSERT INTO processing_status (pdf_id, file_hash, status, risk_decision, updated_at)"
        " VALUES ('pdf-1', 'hash-1', 'risk_assessed', 'non_critical', 'now')"
    )
    db.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert)


def test_revision_version_is_unique_per_run(db):
    add_pdf(db)
    db.execute(
        "INSERT INTO growth_runs (run_id, pdf_id, source_locations_json) VALUES ('run-1', 'pdf-1', '[]')"
    )
    insert = (
        "INSERT INTO run_revisions (revision_id, run_id, version, approved_values_json,"
        " approved_by, approved_at) VALUES (?, 'run-1', 1, '{}', 'Reviewer', 'now')"
    )
    db.execute(insert, ("rev-1",))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert, ("rev-2",))


def test_revision_requires_approver(db):
    add_pdf(db)
    db.execute(
        "INSERT INTO growth_runs (run_id, pdf_id, source_locations_json) VALUES ('run-1', 'pdf-1', '[]')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO run_revisions (revision_id, run_id, version, approved_values_json,"
            " approved_at) VALUES ('rev-1', 'run-1', 1, '{}', 'now')"
        )


def test_registered_pdf_cannot_be_deleted_while_referenced(db):
    add_pdf(db)
    add_draft(db, "Pending review", None)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM source_pdfs WHERE pdf_id = 'pdf-1'")
