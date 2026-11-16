"""Tests for holding drafts (Task 15.3, Requirements 5.4, 10.1 to 10.5). Temporary databases only."""

import pytest

from conftest import query
from review_helpers import REVIEWER, make_review


@pytest.fixture
def review(workspace):
    return make_review(workspace)


def text(response):
    return response.get_data(as_text=True)


@pytest.mark.parametrize("override", [{"hold_reason": ""}, {"hold_reason": "  "}, {"reviewer": ""},
                                      {"reviewer": "Someone Else"}, {"pdf_index": "x", "row": "2"}])
def test_invalid_hold_is_refused_and_nothing_changes(review, override):
    before = review.digest()
    data = {"hold_reason": "unit unclear", "reviewer": REVIEWER, "confirmed": "1", **override}
    assert review.client.post("/drafts/draft-r1/hold", data=data).status_code == 400
    assert review.draft("draft-r1")[:2] == ("Pending review", None)
    assert review.digest() == before and review.actions() == []


def test_unconfirmed_hold_writes_nothing(review):
    before = review.digest()
    assert "Confirm" in text(review.hold("draft-r1", confirmed=False))
    assert review.digest() == before


def test_hold_sets_status_reason_and_records_the_reviewer(review):
    response = review.hold("draft-r1", "Stoichiometry not verified", pdf_index="1", row="1")
    assert response.status_code == 302
    status, reason, *_ = review.draft("draft-r1")
    assert (status, reason) == ("Held", "Stoichiometry not verified (page 1, row 1)")
    [action] = review.actions()
    assert action["action"] == "hold" and action["reviewer"] == REVIEWER and action["draft_id"] == "draft-r1"


def test_held_draft_is_visible_to_the_operator_and_never_in_growth_runs(review):
    review.hold("draft-r1", "Critical issue: ambiguous ratio")
    status_page = text(review.client.get("/status"))
    assert "Critical issue: ambiguous ratio" in status_page
    assert "0 approved · 1 pending · 1 held" in status_page
    assert review.counts()["growth_runs"] == 0
    assert "Critical issue: ambiguous ratio" in text(review.client.get("/drafts"))


def test_held_draft_shows_reason_and_still_allows_correction_and_approval(review):
    review.hold("draft-r1", "Unit unclear")
    page = text(review.client.get("/drafts/draft-r1"))
    assert "Hold reason: <span class=\"hold-reason\">Unit unclear</span>" in page
    assert 'action="/drafts/draft-r1/correct"' in page and 'href="/drafts/draft-r1/approve"' in page
    assert review.correct("draft-r1", "growth_process", "CVT").status_code == 302
    assert review.draft("draft-r1")[0] == "Held"
    assert review.approve("draft-r1").status_code == 302
    assert review.draft("draft-r1")[:2] == ("Approved", None)


def test_rehold_updates_the_reason(review):
    review.hold("draft-r1", "first reason")
    review.hold("draft-r1", "second reason")
    assert review.draft("draft-r1")[1] == "second reason"


def test_approved_draft_cannot_be_held(review):
    query(review.database, "UPDATE draft_runs SET review_status = 'Approved' WHERE draft_id = 'draft-r1'")
    assert review.hold("draft-r1").status_code == 409
