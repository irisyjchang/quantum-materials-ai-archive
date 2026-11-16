"""Tests for approval preconditions (Task 16.3, Requirements 7.2, 8.6, 11.1 to 11.4). Temporary databases only."""

import pytest

from conftest import PDF_BYTES, query
from factories import field, run
from review_helpers import make_review

NONE = dict(value=None, status="missing", raw_value=None, evidence="blank cell")


def text(response):
    return response.get_data(as_text=True)


def unmet(page):
    return page.count('class="unmet-condition"')


def no_composition():
    return run("draft-r1", composition=field(**NONE))


def no_lookup():
    return run("draft-r1", researcher_name=field(**NONE), growth_date=field(**NONE), jc_number=field(**NONE))


def test_valid_draft_has_no_unmet_conditions(workspace):
    review = make_review(workspace)
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert unmet(page) == 0
    assert 'name="verified_stoichiometry"' in page and "<button type=\"submit\"" in page


def test_missing_stoichiometry_disables_approval(workspace):
    review = make_review(workspace, [no_composition()])
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert "No stoichiometry" in page and unmet(page) == 1
    assert '<button type="button" disabled>Approve</button>' in page
    assert "Return to editing" in page


def test_forged_post_without_stoichiometry_is_rejected(workspace):
    review = make_review(workspace, [no_composition()])
    before = review.digest()
    response = review.approve("draft-r1")
    assert response.status_code == 400 and "No stoichiometry" in text(response)
    assert review.counts() == {"growth_runs": 0, "run_revisions": 0}
    assert review.draft("draft-r1")[0] == "Pending review"
    assert review.digest() == before


def test_missing_lookup_value_is_unmet(workspace):
    review = make_review(workspace, [no_lookup()])
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert "No lookup value" in page and unmet(page) == 1


def test_one_lookup_value_is_enough(workspace):
    review = make_review(workspace, [run("draft-r1", researcher_name=field(**NONE), growth_date=field(**NONE))])
    assert unmet(text(review.client.get("/drafts/draft-r1/approve"))) == 0


def test_missing_source_location_is_unmet(workspace):
    review = make_review(workspace)
    query(review.database, "UPDATE draft_runs SET source_locations_json = '[]' WHERE draft_id = 'draft-r1'")
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert "No valid source location" in page and unmet(page) == 1


def test_all_three_failing_gives_three_messages(workspace):
    bad = run("draft-r1", composition=field(**NONE), researcher_name=field(**NONE),
              growth_date=field(**NONE), jc_number=field(**NONE))
    review = make_review(workspace, [bad])
    query(review.database, "UPDATE draft_runs SET source_locations_json = '[]' WHERE draft_id = 'draft-r1'")
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert unmet(page) == 3
    for message in ("No valid source location", "No lookup value", "No stoichiometry"):
        assert message in page


def test_correction_can_satisfy_a_condition(workspace):
    review = make_review(workspace, [no_composition()])
    review.correct("draft-r1", "composition", '{"formula": "MoSe2"}', reason="Compound cell reads MoSe2")
    assert unmet(text(review.client.get("/drafts/draft-r1/approve"))) == 0
    assert review.approve("draft-r1").status_code == 302


def test_invalid_growth_date_is_unmet(workspace):
    review = make_review(workspace, [run("draft-r1", growth_date=field(value="22 Oct 2018"))])
    assert "The growth date must be YYYY-MM or YYYY-MM-DD" in text(review.client.get("/drafts/draft-r1/approve"))


@pytest.mark.parametrize("missing", ["verified_location", "verified_lookup", "verified_stoichiometry"])
def test_every_verification_box_is_required(workspace, missing):
    review = make_review(workspace)
    response = review.approve("draft-r1", **{missing: ""})
    assert response.status_code == 400 and "Confirm that you verified" in text(response)
    assert review.counts()["growth_runs"] == 0


def test_changed_retained_copy_blocks_approval_until_restored(workspace):
    review = make_review(workspace)
    review.storage_path.write_bytes(b"%PDF-1.4\n% altered\n")
    page = text(review.client.get("/drafts/draft-r1/approve"))
    assert "The source PDF cannot be verified" in page
    assert review.approve("draft-r1").status_code == 400
    assert review.counts()["growth_runs"] == 0
    review.storage_path.write_bytes(PDF_BYTES)
    assert review.approve("draft-r1").status_code == 302
    assert review.counts() == {"growth_runs": 1, "run_revisions": 1}
