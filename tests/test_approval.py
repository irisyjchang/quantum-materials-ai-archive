"""Tests for the atomic approval transaction (Task 17.5, Requirements 12.1 to 12.4). Temporary databases only."""

import json

import pytest

from conftest import query
from factories import field, run
from review_app import approval_mapper
from review_app.routes import approve as approve_routes
from review_helpers import REVIEWER, make_review


@pytest.fixture
def review(workspace):
    composition = field(value={"formula": "MoSe2", "transport_agent": "Selenium"}, raw_value="Mo Se2 - Selenium")
    runs = [run("draft-r1", row=1, composition=composition, growth_process=field(value="CVT")),
            run("draft-r2", row=2, growth_date=field(value="2018-10", raw_value="Oct 2018"))]
    return make_review(workspace, runs)


def text(response):
    return response.get_data(as_text=True)


def growth_run(review, draft_id):
    rows = query(review.database,
                 "SELECT run_id, pdf_id, researcher_name, growth_date, date_precision, jc_number, growth_process,"
                 " composition_json, source_locations_json, details_json FROM growth_runs WHERE run_id = ?",
                 (approval_mapper.run_id_for(draft_id),))
    return rows[0] if rows else None


def revisions(review, draft_id):
    return query(review.database,
                 "SELECT revision_id, version, approved_by, approved_at, changes_json, edited_by, edited_at,"
                 " approved_values_json FROM run_revisions WHERE run_id = ? ORDER BY version",
                 (approval_mapper.run_id_for(draft_id),))


# Saved approval (12.1, 12.2) ----------------------------------------------------------------------

def test_approval_asks_for_confirmation_first(review):
    page = text(review.approve("draft-r1", confirmed=False))
    assert f'approve this draft and add it to the archive search as <strong class="confirm-reviewer">{REVIEWER}</strong>' in page
    assert review.counts() == {"growth_runs": 0, "run_revisions": 0}


def test_valid_approval_writes_one_run_and_one_revision(review):
    response = review.approve("draft-r1")
    assert response.status_code == 302 and response.headers["Location"].endswith("/drafts/draft-r1?saved=1")
    assert review.counts() == {"growth_runs": 1, "run_revisions": 1}
    (run_id, pdf_id, name, date, precision, jc, process, composition, locations, details) = growth_run(review, "draft-r1")
    assert pdf_id == review.pdf_id
    assert (date, precision, jc, process) == ("2020-01-16", "day", "JC1302", "CVT")
    assert json.loads(composition) == {"formula": "MoSe2", "transport_agent": "Selenium"}
    assert json.loads(locations) == [{"pdf_index": 1, "row": 1}]
    assert set(json.loads(details)) == {"furnace_cycle", "furnace_layout", "growth_process", "timestamps", "measurements"}
    [(revision_id, version, by, at, changes, edited_by, edited_at, snapshot)] = revisions(review, "draft-r1")
    assert (revision_id, version, by) == (f"{run_id}-v1", 1, REVIEWER)
    assert at.endswith("+00:00")
    assert (changes, edited_by, edited_at) == (None, None, None)
    assert json.loads(snapshot)["draft_id"] == "draft-r1"
    assert review.draft("draft-r1")[0] == "Approved"


def test_saved_is_shown_only_after_commit(review):
    review.approve("draft-r1")
    page = text(review.client.get("/drafts/draft-r1?saved=1"))
    assert f"Saved: approved by {REVIEWER}" in page and "revision 1" in page
    assert "Saved:" not in text(review.client.get("/drafts/draft-r2?saved=1"))


def test_month_precision_date(review):
    review.approve("draft-r2")
    assert growth_run(review, "draft-r2")[3:5] == ("2018-10", "month")


def test_corrections_are_saved_with_the_revision(review):
    review.correct("draft-r1", "jc_number", "0697", reason="# cell reads 0697")
    review.approve("draft-r1")
    assert growth_run(review, "draft-r1")[5] == "0697"
    [(_, _, _, _, changes, edited_by, edited_at, snapshot)] = revisions(review, "draft-r1")
    [change] = json.loads(changes)
    assert (change["field"], change["old_value"], change["new_value"]) == ("jc_number", "JC1302", "0697")
    assert edited_by == REVIEWER and edited_at == change["at"]
    assert json.loads(snapshot)["fields"]["jc_number"]["value"] == "0697"


def test_approved_draft_leaves_the_review_queue(review):
    review.approve("draft-r1")
    page = text(review.client.get("/drafts"))
    assert 'data-draft-id="draft-r1"' not in page and 'data-draft-id="draft-r2"' in page
    assert "1 approved · 1 pending · 0 held" in text(review.client.get("/status"))


# Failure leaves everything unchanged (12.3) ------------------------------------------------------------

def test_failure_after_growth_run_insert_rolls_back_everything(review, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("simulated failure while writing the revision")

    monkeypatch.setattr(approve_routes, "write_revision", explode)
    response = review.approve("draft-r1")
    page = text(response)
    assert response.status_code == 500
    assert "The approval was not saved" in page and "simulated failure" in page
    assert "Saved:" not in page
    assert review.counts() == {"growth_runs": 0, "run_revisions": 0}
    assert review.draft("draft-r1")[0] == "Pending review"
    monkeypatch.undo()
    assert review.approve("draft-r1").status_code == 302
    assert review.counts() == {"growth_runs": 1, "run_revisions": 1}


def test_failure_when_marking_approved_rolls_back_everything(review, monkeypatch):
    monkeypatch.setattr(approve_routes, "mark_approved", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert review.approve("draft-r1").status_code == 500
    assert review.counts() == {"growth_runs": 0, "run_revisions": 0}


# Retry (12.4) ---------------------------------------------------------------------------------------

def test_retry_of_a_committed_approval_returns_the_saved_revision(review):
    state = review.opened_state("draft-r1")
    assert review.approve("draft-r1", state=state).status_code == 302
    retry = review.approve("draft-r1", state=state)
    assert retry.status_code == 302 and retry.headers["Location"].endswith("saved=1")
    assert review.counts() == {"growth_runs": 1, "run_revisions": 1}


def test_approval_page_for_an_approved_draft_redirects_to_it(review):
    review.approve("draft-r1")
    assert review.client.get("/drafts/draft-r1/approve").status_code == 302


def test_unknown_draft_is_not_found(review):
    assert review.client.get("/drafts/nope/approve").status_code == 404
    assert review.approve("nope", state={}).status_code == 404
