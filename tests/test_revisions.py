"""Tests for the approved-run page and revisions (Task 19.3).

Requirements 9.1, 9.4, 11.4, 12.1, 13.1, 29.1 to 29.5. Temporary databases only.
"""

import json

import pytest

from conftest import query
from factories import field, run
from review_app import approval_mapper
from review_app.routes import approve as approve_routes
from review_app.search.query import SearchCriteria, search
from review_helpers import REVIEWER, VERIFIED, make_review

RUN_ID = approval_mapper.run_id_for("draft-r1")


@pytest.fixture
def approved(workspace):
    composition = field(value={"formula": "MoSe2"}, raw_value="Mo Se2")
    review = make_review(workspace, [run("draft-r1", researcher_name=field(value="Zhong"), composition=composition),
                                     run("draft-r2", row=2)])
    assert review.approve("draft-r1").status_code == 302
    return review


def text(response):
    return response.get_data(as_text=True)


def revise(review, field_key="researcher_name", new_value="Zhong Lab", reason="Header reads Zhong Lab",
           opened_version="1", confirmed=True, **extra):
    data = {"field": field_key, "new_value": new_value, "reason": reason, "opened_version": opened_version,
            "reviewer": REVIEWER, **VERIFIED, **extra}
    if confirmed:
        data["confirmed"] = "1"
    return review.client.post(f"/runs/{RUN_ID}/revise", data=data)


def revisions(review):
    return query(review.database, "SELECT revision_id, version, approved_values_json, changes_json, edited_by,"
                                  " edited_at, approved_by, approved_at FROM run_revisions ORDER BY version")


def growth_name(review):
    return query(review.database, "SELECT researcher_name FROM growth_runs WHERE run_id = ?", (RUN_ID,))[0][0]


# Run page (19.1) ---------------------------------------------------------------------------------

def test_run_page_shows_values_pdf_and_revision_history(approved):
    page = text(approved.client.get(f"/runs/{RUN_ID}"))
    assert "Approved run from log-1-901.pdf" in page
    assert '<li class="revision" data-version="1">' in page
    assert f"approved by {REVIEWER}" in page and "Approved as extracted" in page
    assert f'src="/pdf/{approved.pdf_id}#page=1"' in page and "page 1, row 1</strong>" in page
    assert 'data-environment="test"' in page


def test_approved_draft_links_to_its_run(approved):
    assert f'href="/runs/{RUN_ID}"' in text(approved.client.get("/drafts/draft-r1"))


def test_unknown_run_is_not_found(approved):
    assert approved.client.get("/runs/run-nope").status_code == 404
    assert approved.client.post("/runs/run-nope/revise", data={}).status_code == 404


# Revision (19.2, 29.1, 29.2, 29.3) ---------------------------------------------------------------

def test_revision_adds_version_2_and_keeps_version_1_unchanged(approved):
    [before_v1] = revisions(approved)
    response = revise(approved)
    assert response.status_code == 302 and response.headers["Location"].endswith(f"/runs/{RUN_ID}?revised=1")
    v1, v2 = revisions(approved)
    assert v1 == before_v1
    revision_id, version, snapshot, changes, edited_by, edited_at, approved_by, approved_at = v2
    assert (revision_id, version, edited_by, approved_by) == (f"{RUN_ID}-v2", 2, REVIEWER, REVIEWER)
    [change] = json.loads(changes)
    assert (change["field"], change["old_value"], change["new_value"], change["reason"]) == (
        "researcher_name", "Zhong", "Zhong Lab", "Header reads Zhong Lab")
    assert json.loads(snapshot)["fields"]["researcher_name"]["value"] == "Zhong Lab"
    assert growth_name(approved) == "Zhong Lab"
    assert query(approved.database, "SELECT count(*) FROM growth_runs")[0][0] == 1


def test_search_returns_the_revised_value_for_the_same_run(approved):
    revise(approved)
    from review_app.app import create_app  # noqa: F401  (search is a pure query over the database)
    import sqlite3
    connection = sqlite3.connect(approved.database)
    try:
        results = search(connection, SearchCriteria(name="zhong lab"))
    finally:
        connection.close()
    assert [result["run_id"] for result in results] == [RUN_ID]
    page = text(approved.client.get("/runs?name=Zhong+Lab"))
    assert f'data-run-id="{RUN_ID}"' in page


def test_history_lists_revisions_in_order_with_changes(approved):
    revise(approved)
    page = text(approved.client.get(f"/runs/{RUN_ID}?revised=1"))
    assert page.index('data-version="1"') < page.index('data-version="2"')
    assert "Saved: revision 2" in page
    assert "Zhong</code>" in page and "Zhong Lab</code>" in page and "Header reads Zhong Lab" in page


# Refusals write nothing (9.1, 9.4, 11.4) -----------------------------------------------------------

@pytest.mark.parametrize("override, message", [
    ({"reason": ""}, "Give a reason"),
    ({"field": "technique"}, "Choose which field"),
    ({"field": "composition", "new_value": ""}, "No stoichiometry"),
    ({"field": "researcher_name", "new_value": "Zhong"}, "same as the approved value"),
    ({"verified_stoichiometry": ""}, "Confirm that you verified"),
    ({"field": "growth_date", "new_value": "Oct 2018"}, "YYYY-MM"),
])
def test_invalid_revision_is_refused_and_nothing_is_written(approved, override, message):
    before = approved.digest()
    response = revise(approved, **override)
    assert response.status_code == 400 and message in text(response)
    assert len(revisions(approved)) == 1 and approved.digest() == before


@pytest.mark.parametrize("reviewer", ["", "Someone Else"])
def test_revision_needs_an_authorized_reviewer(approved, reviewer):
    before = approved.digest()
    assert revise(approved, reviewer=reviewer).status_code == 400
    assert approved.digest() == before


def test_unconfirmed_revision_shows_confirmation_and_writes_nothing(approved):
    before = approved.digest()
    page = text(revise(approved, confirmed=False))
    assert "save a revision of this run" in page and approved.digest() == before


# Stale view (29.4) and failure (29.5) --------------------------------------------------------------

def test_revision_from_a_stale_view_is_refused_until_resubmitted(approved):
    assert revise(approved, new_value="Zhong Lab", opened_version="1").status_code == 302
    stale = revise(approved, new_value="Zhong Group", opened_version="1")
    assert stale.status_code == 409 and "revised after you opened it" in text(stale)
    assert [row[1] for row in revisions(approved)] == [1, 2] and growth_name(approved) == "Zhong Lab"
    assert revise(approved, new_value="Zhong Group", opened_version="2").status_code == 302
    assert [row[1] for row in revisions(approved)] == [1, 2, 3] and growth_name(approved) == "Zhong Group"


def test_failure_inside_the_revision_transaction_changes_nothing(approved, monkeypatch):
    before_runs = query(approved.database, "SELECT * FROM growth_runs")
    before_revisions = revisions(approved)
    monkeypatch.setattr(approve_routes, "write_revision",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated failure")))
    response = revise(approved)
    assert response.status_code == 500 and "simulated failure" in text(response)
    assert query(approved.database, "SELECT * FROM growth_runs") == before_runs
    assert revisions(approved) == before_revisions
