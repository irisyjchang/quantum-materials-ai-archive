"""Tests for reviewer clearance of held PDFs (Task 12.3).

Requirements 6.1 to 6.5, 14.4, 1.6, 7.1 to 7.3. Temporary databases and a
temporary reviewer name ("Reviewer A") from the test config.
"""

import hashlib
from pathlib import Path

import pytest

import staging
from conftest import query
from factories import PLACEHOLDER_DRIVE_ID
from review_app.app import create_app

ISSUES = [{"reason": "ambiguous ratio", "source_location": {"pdf_index": 1, "row": 2}}]
NOTE = "Ratio basis confirmed with the researcher"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def held(workspace):
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet("critical", ISSUES), database=database) == 0
    pdf_id = query(database, "SELECT pdf_id FROM source_pdfs")[0][0]
    client = create_app("test", root=workspace.root).test_client()
    return workspace, database, pdf_id, client


def clearance(database, pdf_id):
    return query(database, "SELECT status, clearance_by, clearance_at, clearance_note, reason"
                           " FROM processing_status WHERE pdf_id = ?", (pdf_id,))[0]


def clear(client, pdf_id, **form):
    return client.post(f"/status/{pdf_id}/clear", data=form)


# The prompt (6.1, 14.4) --------------------------------------------------------------------

def test_held_pdf_shows_issues_and_clearance_form(held):
    _, _, pdf_id, client = held
    page = client.get("/status").get_data(as_text=True)
    assert "ambiguous ratio" in page and "(page 1, row 2)" in page
    assert f'action="/status/{pdf_id}/clear"' in page
    assert 'name="clearance_note"' in page
    assert '<option value="Reviewer A">Reviewer A</option>' in page
    assert "resume" in page and "same PDF version" in page


# Refusals write nothing (6.2, 7.1, 7.3) -----------------------------------------------------

@pytest.mark.parametrize("form, status", [
    ({"clearance_note": NOTE}, 400),
    ({"clearance_note": NOTE, "reviewer": ""}, 400),
    ({"clearance_note": NOTE, "reviewer": "Someone Else", "confirmed": "1"}, 400),
    ({"clearance_note": "   ", "reviewer": "Reviewer A", "confirmed": "1"}, 400),
    ({"reviewer": "Reviewer A", "confirmed": "1"}, 400),
])
def test_invalid_clearance_is_refused_and_nothing_is_written(held, form, status):
    _, database, pdf_id, client = held
    before = digest(database)
    response = clear(client, pdf_id, **form)
    assert response.status_code == status
    assert "Nothing was recorded" in response.get_data(as_text=True)
    assert clearance(database, pdf_id)[:4] == ("held_pending_clearance", None, None, None)
    assert digest(database) == before


def test_valid_name_asks_for_confirmation_first(held):
    _, database, pdf_id, client = held
    before = digest(database)
    page = clear(client, pdf_id, clearance_note=NOTE, reviewer="Reviewer A").get_data(as_text=True)
    assert "You are about to clear log-1-901.pdf for extraction as" in page
    assert f'<input type="hidden" name="clearance_note" value="{NOTE}">' in page
    assert clearance(database, pdf_id)[0] == "held_pending_clearance"
    assert digest(database) == before


def test_pdf_that_is_not_held_cannot_be_cleared(workspace):
    database = workspace.database("test")
    workspace.risk_assess(workspace.risk_packet(), database=database)
    pdf_id = query(database, "SELECT pdf_id FROM source_pdfs")[0][0]
    client = create_app("test", root=workspace.root).test_client()
    response = clear(client, pdf_id, clearance_note=NOTE, reviewer="Reviewer A", confirmed="1")
    assert response.status_code == 409
    assert clearance(database, pdf_id)[:2] == ("risk_assessed", None)


def test_unknown_pdf_is_not_found(held):
    _, _, _, client = held
    assert clear(client, "pdf-unknown", clearance_note=NOTE, reviewer="Reviewer A", confirmed="1").status_code == 404


# Successful clearance (6.3, 6.4) ------------------------------------------------------------

def test_confirmed_clearance_records_reviewer_note_and_time(held):
    _, database, pdf_id, client = held
    response = clear(client, pdf_id, clearance_note=f"  {NOTE} ", reviewer="Reviewer A", confirmed="1")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/status?cleared={pdf_id}")
    status, by, at, note, reason = clearance(database, pdf_id)
    assert (status, by, note, reason) == ("cleared", "Reviewer A", NOTE, None)
    assert at and at.endswith("+00:00")
    page = client.get(f"/status?cleared={pdf_id}").get_data(as_text=True)
    assert "Saved: log-1-901.pdf is cleared for extraction by Reviewer A" in page
    assert "Cleared by Reviewer A" in page


def test_after_clearance_check_gate_passes_and_stage_drafts_accepts(held):
    workspace, database, pdf_id, client = held
    clear(client, pdf_id, clearance_note=NOTE, reviewer="Reviewer A", confirmed="1")
    assert staging.main(["check-gate", PLACEHOLDER_DRIVE_ID, workspace.pdf_hash, str(database)]) == 0
    assert workspace.stage_drafts(workspace.extraction_packet(), database=database) == 0
    assert query(database, "SELECT review_status FROM draft_runs") == [("Pending review",)]


def test_second_clearance_is_refused(held):
    _, database, pdf_id, client = held
    clear(client, pdf_id, clearance_note=NOTE, reviewer="Reviewer A", confirmed="1")
    response = clear(client, pdf_id, clearance_note="again", reviewer="Reviewer A", confirmed="1")
    assert response.status_code == 409
    assert clearance(database, pdf_id)[3] == NOTE


# Exact version only (6.5, 1.6) --------------------------------------------------------------

def test_replacement_version_is_not_cleared_by_the_old_clearance(held):
    workspace, database, old_id, client = held
    clear(client, old_id, clearance_note=NOTE, reviewer="Reviewer A", confirmed="1")
    replacement, new_hash = workspace.make_pdf("log-1-901.pdf", b"%PDF-1.4\n% replacement scan\n")
    workspace.risk_assess(workspace.risk_packet("critical", ISSUES, file_hash=new_hash),
                          database=database, source_pdf=replacement)
    new_id = query(database, "SELECT pdf_id FROM source_pdfs WHERE file_hash = ?", (new_hash,))[0][0]
    assert clearance(database, new_id)[:4] == ("held_pending_clearance", None, None, None)
    assert staging.main(["check-gate", PLACEHOLDER_DRIVE_ID, new_hash, str(database)]) == 1
    page = client.get("/status").get_data(as_text=True)
    assert f'action="/status/{new_id}/clear"' in page
    assert f'action="/status/{old_id}/clear"' not in page
