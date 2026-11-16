"""Tests for the draft list, draft detail, and source-PDF viewer (Task 13.5).

Requirements 3.4, 8.1 to 8.4, 8.6, 10.3. Temporary databases only.
"""

from pathlib import Path

import pytest

from conftest import PDF_BYTES, query
from factories import field, run
from review_app.app import create_app


@pytest.fixture
def staged(workspace):
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0
    spanning = run("draft-p1-r4", row=4,
                   composition=field(value={"formula": "MoSe2"}, raw_value="Mo Se2 - Selenium",
                                     evidence="PDF page 1, Calculated table, row 4, Compound cell"))
    spanning["source_locations"] = [{"pdf_index": 1, "row": 4}, {"pdf_index": 2, "row": 1}]
    runs = [run("draft-p1-r1", row=1), spanning]
    assert workspace.stage_drafts(workspace.extraction_packet(runs), database=database) == 0
    pdf_id, storage_path = query(database, "SELECT pdf_id, storage_path FROM source_pdfs")[0]
    client = create_app("test", root=workspace.root).test_client()
    return database, pdf_id, Path(storage_path), client


def text(response):
    return response.get_data(as_text=True)


# Draft list (3.4, 10.3) ------------------------------------------------------------------------

def test_list_shows_pending_and_held_but_not_approved(staged):
    database, _, _, client = staged
    query(database, "UPDATE draft_runs SET review_status = 'Held', hold_reason = 'unit unclear'"
                    " WHERE draft_id = 'draft-p1-r1'")
    page = text(client.get("/drafts"))
    assert 'data-draft-id="draft-p1-r1"' in page and "unit unclear" in page
    assert 'data-draft-id="draft-p1-r4"' in page and "page 1, row 4; page 2, row 1" in page
    query(database, "UPDATE draft_runs SET review_status = 'Approved' WHERE draft_id = 'draft-p1-r4'")
    assert 'data-draft-id="draft-p1-r4"' not in text(client.get("/drafts"))


def test_list_links_to_each_draft(staged):
    _, _, _, client = staged
    assert 'href="/drafts/draft-p1-r1"' in text(client.get("/drafts"))


# Draft detail (8.1) -----------------------------------------------------------------------------

def test_detail_shows_every_field_with_status_raw_value_and_evidence(staged):
    _, _, _, client = staged
    response = client.get("/drafts/draft-p1-r4")
    page = text(response)
    assert response.status_code == 200
    for key in ("researcher_name", "growth_date", "jc_number", "composition", "furnace_cycle",
                "furnace_layout", "growth_process", "timestamps", "measurements"):
        assert f'data-field="{key}"' in page
    assert "Mo Se2 - Selenium" in page
    assert "&#34;formula&#34;: &#34;MoSe2&#34;" in page or '"formula": "MoSe2"' in page
    assert "PDF page 1, Calculated table, row 4, Compound cell" in page
    assert "Status: <strong>Pending review</strong>" in page


def test_unknown_draft_is_not_found(staged):
    assert staged[3].get("/drafts/no-such-draft").status_code == 404


# Viewer at page and row (8.2, 8.4) ------------------------------------------------------------

def test_viewer_opens_the_recorded_page_with_the_row_label(staged):
    _, pdf_id, _, client = staged
    page = text(client.get("/drafts/draft-p1-r4"))
    assert f'src="/pdf/{pdf_id}#page=1"' in page
    assert "page 1, row 4</strong>" in page
    assert 'href="?loc=1"' in page


def test_every_recorded_location_is_reachable(staged):
    _, pdf_id, _, client = staged
    page = text(client.get("/drafts/draft-p1-r4?loc=1"))
    assert f'src="/pdf/{pdf_id}#page=2"' in page
    assert "page 2, row 1</strong>" in page
    assert 'href="?loc=0"' in page


def test_out_of_range_location_falls_back_to_the_first(staged):
    _, pdf_id, _, client = staged
    assert f'src="/pdf/{pdf_id}#page=1"' in text(client.get("/drafts/draft-p1-r4?loc=9"))
    assert f'src="/pdf/{pdf_id}#page=1"' in text(client.get("/drafts/draft-p1-r4?loc=x"))


def test_pdf_route_serves_the_exact_retained_bytes(staged):
    _, pdf_id, _, client = staged
    response = client.get(f"/pdf/{pdf_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data == PDF_BYTES
    assert "inline" in response.headers.get("Content-Disposition", "inline")


def test_pdf_route_for_unknown_pdf_is_not_found(staged):
    assert staged[3].get("/pdf/pdf-unknown").status_code == 404


# Missing or changed retained copy (8.3, 8.6) ------------------------------------------------------

def test_missing_copy_shows_an_error_but_the_page_loads(staged):
    _, pdf_id, storage_path, client = staged
    storage_path.unlink()
    response = client.get("/drafts/draft-p1-r1")
    page = text(response)
    assert response.status_code == 200
    assert 'data-integrity="missing"' in page
    assert "Source PDF unavailable" in page and "Approval of drafts from this PDF is blocked" in page
    assert "<iframe" not in page
    assert 'data-field="composition"' in page
    assert client.get(f"/pdf/{pdf_id}").status_code == 409


def test_changed_copy_shows_a_warning_and_blocks_approval(staged):
    _, pdf_id, storage_path, client = staged
    storage_path.write_bytes(b"%PDF-1.4\n% altered\n")
    page = text(client.get("/drafts/draft-p1-r1"))
    assert 'data-integrity="mismatch"' in page
    assert "Retained copy changed" in page and "Approval of drafts from this PDF is blocked" in page
    assert "<iframe" not in page
    assert client.get(f"/pdf/{pdf_id}").status_code == 409


def test_intact_copy_is_not_blocked(staged):
    page = text(staged[3].get("/drafts/draft-p1-r1"))
    assert 'data-integrity="ok"' in page and "blocked" not in page


def test_detail_escapes_extracted_text(workspace):
    database = workspace.database("test")
    workspace.risk_assess(workspace.risk_packet(), database=database)
    bad = run("draft-x")
    bad["fields"]["growth_process"] = field(raw_value="<script>alert(1)</script>", evidence="<b>x</b>")
    workspace.stage_drafts(workspace.extraction_packet([bad]), database=database)
    page = text(create_app("test", root=workspace.root).test_client().get("/drafts/draft-x"))
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
