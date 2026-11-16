"""Tests for the processing status view (Tasks 11.3, 11.4).

Requirements 14.1, 14.2, 14.3, 14.5, 14.7, 10.4, 30.6. Rows are seeded with SQL in
temporary databases, so these tests do not depend on the hold or approval routes.
"""

import json

import pytest

from conftest import query
from db.init_db import initialize
from review_app.app import create_app

ISSUES = json.dumps([{"reason": "ambiguous ratio", "source_location": {"pdf_index": 1, "row": 2}},
                     {"reason": "page unreadable", "source_location": None}])


@pytest.fixture
def setup(tmp_path):
    for name in ("test", "archive"):
        initialize(tmp_path / f"{name}.sqlite")
    checklist = tmp_path / "test_checklist.json"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"reviewers": [], "checklist_path": str(checklist)}), encoding="utf-8")
    return tmp_path, config, checklist


def page(setup, env_name="test"):
    root, config, _ = setup
    response = create_app(env_name, root=root, config_path=config).test_client().get("/status")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def add_pdf(database, pdf_id, filename="log-1-901.pdf", drive_file_id="placeholder-drive-1",
            file_hash="a" * 64, status="extraction_complete", decision="non_critical",
            reason=None, issues=None, updated_at="2026-11-16T10:00:00+00:00"):
    query(database, "INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash, storage_path)"
                    " VALUES (?, ?, ?, ?, '/tmp/retained.pdf')", (pdf_id, filename, drive_file_id, file_hash))
    query(database, "INSERT INTO processing_status (pdf_id, file_hash, status, risk_decision, issues_json, reason,"
                    " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
          (pdf_id, file_hash, status, decision, issues, reason, updated_at))


def add_draft(database, draft_id, pdf_id, row, status="Pending review", hold_reason=None):
    query(database, "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json,"
                    " review_status, hold_reason, updated_at) VALUES (?, ?, ?, '{}', ?, ?, 'now')",
          (draft_id, pdf_id, json.dumps([{"pdf_index": 1, "row": row}]), status, hold_reason))


def row_html(html, pdf_id):
    """The status table row for one PDF."""
    marker = html.index(f'data-pdf-id="{pdf_id}"')
    start = html.rindex("<tr", 0, marker)
    return html[start:html.index("</tr>", marker)]


# Counts (14.2, 14.3) -----------------------------------------------------------------------

def test_counts_follow_each_review_status_change(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-1")
    add_draft(database, "d1", "pdf-1", 1)
    add_draft(database, "d2", "pdf-1", 2)
    assert "0 approved · 2 pending · 0 held" in row_html(page(setup), "pdf-1")

    query(database, "UPDATE draft_runs SET review_status = 'Held', hold_reason = 'unit unclear' WHERE draft_id = 'd1'")
    query(database, "UPDATE draft_runs SET review_status = 'Approved' WHERE draft_id = 'd2'")
    assert "1 approved · 0 pending · 1 held" in row_html(page(setup), "pdf-1")


def test_pdf_without_drafts_shows_no_counts(setup):
    add_pdf(setup[0] / "test.sqlite", "pdf-1", status="risk_assessed")
    row = row_html(page(setup), "pdf-1")
    assert "No drafts yet" in row and "approved ·" not in row


def test_counts_are_per_pdf(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-1")
    add_pdf(database, "pdf-2", filename="log-2-902.pdf", drive_file_id="placeholder-drive-2", file_hash="b" * 64)
    add_draft(database, "d1", "pdf-1", 1)
    add_draft(database, "d2", "pdf-2", 1, status="Approved")
    html = page(setup)
    assert "0 approved · 1 pending · 0 held" in row_html(html, "pdf-1")
    assert "1 approved · 0 pending · 0 held" in row_html(html, "pdf-2")


# Rows and reasons (14.1, 14.7) ---------------------------------------------------------------

def test_every_registered_version_is_listed_with_tier_and_status(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-1", status="risk_assessed")
    add_pdf(database, "pdf-2", drive_file_id="placeholder-drive-1", file_hash="c" * 64,
            status="held_pending_clearance", decision="critical", reason="Held pending clearance: ambiguous ratio",
            issues=ISSUES)
    html = page(setup)
    assert html.count('class="pdf-row') == 2
    assert "Non-critical" in row_html(html, "pdf-1") and "Assessed, ready for extraction" in row_html(html, "pdf-1")
    held = row_html(html, "pdf-2")
    assert "Critical" in held and "Held pending clearance" in held
    assert "hash cccccccccccc" in held


def test_empty_database_says_nothing_processed(setup):
    assert "No source PDFs have been processed" in page(setup)


# Held and failed outcomes (14.5, 10.4) -------------------------------------------------------

def test_held_and_failed_pdfs_are_visually_distinct(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-held", status="held_pending_clearance", decision="uncertain",
            reason="Held pending clearance: page unreadable", issues=ISSUES)
    add_pdf(database, "pdf-failed", filename="log-2-902.pdf", drive_file_id="placeholder-drive-2",
            file_hash="b" * 64, status="technical_failure", reason="stage-drafts failed: disk full")
    html = page(setup)
    held, failed = row_html(html, "pdf-held"), row_html(html, "pdf-failed")
    assert "outcome-held_pending_clearance" in held and "outcome-technical_failure" not in held
    assert "outcome-technical_failure" in failed
    assert "Held pending clearance: page unreadable" in held
    assert "Retryable" in failed and "stage-drafts failed: disk full" in failed
    assert "Retryable" not in held


def test_held_pdf_lists_its_issues_and_a_clearance_slot(setup):
    add_pdf(setup[0] / "test.sqlite", "pdf-held", status="held_pending_clearance", decision="critical",
            issues=ISSUES)
    html = page(setup)
    detail = html[html.index('class="detail-row held-detail"'):]
    assert "ambiguous ratio" in detail and "(page 1, row 2)" in detail
    assert "page unreadable" in detail
    assert 'class="clearance-slot" data-pdf-id="pdf-held"' in detail


def test_held_drafts_show_their_reasons_to_the_operator(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-1")
    add_draft(database, "d1", "pdf-1", 3, status="Held", hold_reason="stoichiometry not verified")
    html = page(setup)
    assert "Held drafts" in html
    assert "page 1, row 3" in html and "stoichiometry not verified" in html


def test_page_escapes_stored_text(setup):
    add_pdf(setup[0] / "test.sqlite", "pdf-1", status="technical_failure", reason="<script>alert(1)</script>")
    html = page(setup)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# Reserved label (30.6) -----------------------------------------------------------------------

def reserve(setup, *ids):
    setup[2].write_text(json.dumps({"acceptance": [{"drive_file_id": i} for i in ids]}), encoding="utf-8")


def test_reserved_pdf_is_labelled_in_test(setup):
    database = setup[0] / "test.sqlite"
    add_pdf(database, "pdf-1", drive_file_id="placeholder-reserved")
    add_pdf(database, "pdf-2", filename="log-2-902.pdf", drive_file_id="placeholder-open", file_hash="b" * 64)
    reserve(setup, "placeholder-reserved")
    html = page(setup)
    assert "Reserved (acceptance)" in row_html(html, "pdf-1")
    assert "Reserved (acceptance)" not in row_html(html, "pdf-2")


def test_no_reserved_label_in_archive(setup):
    add_pdf(setup[0] / "archive.sqlite", "pdf-1", drive_file_id="placeholder-reserved")
    reserve(setup, "placeholder-reserved")
    assert "Reserved (acceptance)" not in page(setup, "archive")


def test_no_reserved_label_when_checklist_is_missing(setup):
    add_pdf(setup[0] / "test.sqlite", "pdf-1", drive_file_id="placeholder-reserved")
    assert "Reserved (acceptance)" not in page(setup)


def test_unreadable_checklist_shows_a_warning_not_an_error(setup):
    add_pdf(setup[0] / "test.sqlite", "pdf-1")
    setup[2].write_text("{broken", encoding="utf-8")
    assert "Reserved acceptance PDFs cannot be labelled" in page(setup)


def test_status_page_shows_the_environment_banner(setup):
    assert 'data-environment="archive"' in page(setup, "archive")
