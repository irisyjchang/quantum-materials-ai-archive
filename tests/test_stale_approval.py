"""Tests for stale-approval protection (Task 18.3, Requirements 13.1, 13.2). Temporary databases only.

"Second session" actions are made through the app while the first session
still holds the state it captured when it opened the approval page.
"""

import json

import pytest

from conftest import query
from review_app import approval_mapper
from review_helpers import make_review


@pytest.fixture
def review(workspace):
    return make_review(workspace)


def text(response):
    return response.get_data(as_text=True)


def test_first_approval_carries_no_version(review):
    state = review.opened_state("draft-r1")
    assert state["opened_updated_at"] and state["opened_version"] == ""
    assert review.approve("draft-r1", state=state).status_code == 302


def test_correction_in_another_session_forces_reload_and_confirmation(review):
    first_session = review.opened_state("draft-r1")
    review.correct("draft-r1", "growth_process", "Flux Growth", reason="decant note in margin")
    before = review.digest()
    response = review.approve("draft-r1", state=first_session)
    page = text(response)
    assert response.status_code == 409
    assert "This draft changed after you opened it" in page and "Nothing was saved" in page
    assert review.counts() == {"growth_runs": 0, "run_revisions": 0}
    assert review.digest() == before
    fresh = review.opened_state("draft-r1")
    assert fresh["opened_updated_at"] != first_session["opened_updated_at"]
    assert f'value="{fresh["opened_updated_at"]}"' in page
    assert review.approve("draft-r1", state=fresh).status_code == 302
    assert json.loads(query(review.database, "SELECT details_json FROM growth_runs")[0][0])[
        "growth_process"]["value"] == "Flux Growth"


def test_hold_in_another_session_forces_reload(review):
    first_session = review.opened_state("draft-r1")
    review.hold("draft-r1", "ratio basis unclear")
    response = review.approve("draft-r1", state=first_session)
    assert response.status_code == 409
    assert review.draft("draft-r1")[:2] == ("Held", "ratio basis unclear")
    assert review.counts()["run_revisions"] == 0


def test_missing_state_is_treated_as_stale(review):
    assert review.approve("draft-r1", state={"opened_updated_at": "", "opened_version": ""}).status_code == 409
    assert review.counts()["growth_runs"] == 0


def seed_revision(review, draft_id, version):
    run_id = approval_mapper.run_id_for(draft_id)
    if version == 1:
        query(review.database, "INSERT INTO growth_runs (run_id, pdf_id, composition_json, source_locations_json)"
                               " VALUES (?, ?, '{}', '[]')", (run_id, review.pdf_id))
    query(review.database, "INSERT INTO run_revisions (revision_id, run_id, version, approved_values_json,"
                           " approved_by, approved_at) VALUES (?, ?, ?, '{}', 'Reviewer A', 'now')",
          (approval_mapper.revision_id_for(run_id, version), run_id, version))


def test_changed_version_forces_confirmation_and_never_duplicates(review):
    seed_revision(review, "draft-r1", 1)
    first_session = review.opened_state("draft-r1")
    assert first_session["opened_version"] == "1"
    seed_revision(review, "draft-r1", 2)
    response = review.approve("draft-r1", state=first_session)
    assert response.status_code == 409
    versions = [row[0] for row in query(review.database, "SELECT version FROM run_revisions ORDER BY version")]
    assert versions == [1, 2]
    fresh = review.opened_state("draft-r1")
    assert fresh["opened_version"] == "2"
    assert review.approve("draft-r1", state=fresh).status_code == 302
    versions = [row[0] for row in query(review.database, "SELECT version FROM run_revisions ORDER BY version")]
    assert versions == [1, 2, 3]
    assert query(review.database, "SELECT count(*) FROM growth_runs")[0][0] == 1


def test_stale_page_after_another_approval_returns_the_saved_revision(review):
    first_session = review.opened_state("draft-r1")
    second_session = review.opened_state("draft-r1")
    assert review.approve("draft-r1", state=second_session).status_code == 302
    retry = review.approve("draft-r1", state=first_session)
    assert retry.status_code == 302 and retry.headers["Location"].endswith("saved=1")
    assert review.counts() == {"growth_runs": 1, "run_revisions": 1}


def test_updated_at_always_moves_forward():
    """Regression: a change in the same instant (or with a clock behind the stored value) still changes updated_at."""
    from datetime import datetime

    from staging_lib.clock import later_than

    future = "2099-01-01T00:00:00.000000+00:00"
    bumped = later_than(future)
    assert datetime.fromisoformat(bumped) > datetime.fromisoformat(future)
    second_precision = "2099-01-01T00:00:00+00:00"
    assert later_than(second_precision) != second_precision
    assert later_than(None) and later_than("not a timestamp")
