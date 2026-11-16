"""Tests for field correction (Task 14.4, Requirements 7.1, 9.1 to 9.4). Temporary databases only."""

import json

import pytest

from conftest import query
from factories import field, run
from review_helpers import REVIEWER, make_review


@pytest.fixture
def review(workspace):
    return make_review(workspace)


def text(response):
    return response.get_data(as_text=True)


# Saved correction (9.2, 9.3) -----------------------------------------------------------------

def test_correction_is_recorded_and_original_json_is_unchanged(review):
    before_original = review.draft("draft-r1")[3]
    before_updated = review.draft("draft-r1")[2]
    response = review.correct("draft-r1", "researcher_name", "Zhong", reason="Header reads Zhong")
    assert response.status_code == 302
    assert review.draft("draft-r1")[3] == before_original
    assert review.draft("draft-r1")[2] != before_updated
    [record] = review.corrections("draft-r1")
    assert record["field"] == "researcher_name"
    assert record["old_value"] == "value" and record["new_value"] == "Zhong"
    assert record["reason"] == "Header reads Zhong"
    assert record["source_location"] == {"pdf_index": 1, "row": 1}
    assert record["reviewer"] == REVIEWER and record["at"].endswith("+00:00")


def test_detail_shows_the_corrected_value_and_who_corrected_it(review):
    review.correct("draft-r1", "researcher_name", "Zhong", reason="Header reads Zhong")
    page = text(review.client.get("/drafts/draft-r1?corrected=researcher_name"))
    block = page[page.index('data-field="researcher_name"'):]
    block = block[:block.index("</div>")]
    assert "<pre>Zhong</pre>" in block and "corrected" in block
    assert f"Corrected by {REVIEWER}" in page and "Header reads Zhong" in page
    assert "Correction saved for researcher name" in page


def test_explicit_page_and_row_are_recorded(review):
    review.correct("draft-r1", "growth_process", "CVT", pdf_index="1", row="7")
    assert review.corrections("draft-r1")[0]["source_location"] == {"pdf_index": 1, "row": 7}


def test_corrections_accumulate_in_order(review):
    review.correct("draft-r1", "jc_number", "JC1303")
    review.correct("draft-r1", "jc_number", "JC1304")
    records = review.corrections("draft-r1")
    assert [(r["old_value"], r["new_value"]) for r in records] == [("JC1302", "JC1303"), ("JC1303", "JC1304")]


# Value rules ------------------------------------------------------------------------------------

def test_text_fields_stay_text_with_leading_zeros(review):
    review.correct("draft-r1", "jc_number", "0697")
    assert review.corrections("draft-r1")[0]["new_value"] == "0697"


def test_structured_field_takes_json(workspace):
    composition = field(value={"formula": "MoSe2"}, raw_value="Mo Se2")
    review = make_review(workspace, [run("draft-r1", composition=composition)])
    assert review.correct("draft-r1", "composition", '{"formula": "MoSe2", "ratio": "1:2"}').status_code == 302
    assert review.corrections("draft-r1")[0]["new_value"] == {"formula": "MoSe2", "ratio": "1:2"}
    assert review.correct("draft-r1", "composition", "MoSe2").status_code == 400
    assert review.correct("draft-r1", "composition", '{"formula": ').status_code == 400


@pytest.mark.parametrize("value, ok", [("2018-10", True), ("2018-10-22", True), ("2018-13", False),
                                       ("2018-02-30", False), ("22 Oct 2018", False)])
def test_growth_date_format_is_checked(review, value, ok):
    assert (review.correct("draft-r1", "growth_date", value).status_code == 302) is ok


def test_empty_value_clears_the_field(review):
    review.correct("draft-r1", "measurements", "")
    assert review.corrections("draft-r1")[0]["new_value"] is None


def test_unchanged_value_is_refused(review):
    assert review.correct("draft-r1", "jc_number", "JC1302").status_code == 400


# Refusals write nothing (9.1, 9.4, 7.1) -------------------------------------------------------------

@pytest.mark.parametrize("override, status", [
    ({"reason": ""}, 400),
    ({"reason": "   "}, 400),
    ({"field": "technique"}, 400),
    ({"reviewer": ""}, 400),
    ({"reviewer": "Someone Else"}, 400),
    ({"pdf_index": "0", "row": "1"}, 400),
    ({"pdf_index": "one", "row": "1"}, 400),
])
def test_invalid_correction_is_refused_and_nothing_is_written(review, override, status):
    before = review.digest()
    data = {"field": "researcher_name", "new_value": "Zhong", "reason": "Header reads Zhong",
            "reviewer": REVIEWER, "confirmed": "1", **override}
    response = review.client.post("/drafts/draft-r1/correct", data=data)
    assert response.status_code == status
    assert review.corrections("draft-r1") == []
    assert review.digest() == before


def test_unconfirmed_correction_shows_confirmation_and_writes_nothing(review):
    before = review.digest()
    page = text(review.correct("draft-r1", "researcher_name", "Zhong", confirmed=False))
    assert f"as <strong class=\"confirm-reviewer\">{REVIEWER}</strong>" in page
    assert review.corrections("draft-r1") == [] and review.digest() == before


def test_approved_draft_cannot_be_corrected(review):
    query(review.database, "UPDATE draft_runs SET review_status = 'Approved' WHERE draft_id = 'draft-r1'")
    assert review.correct("draft-r1", "researcher_name", "Zhong").status_code == 409


def test_unknown_draft_is_not_found(review):
    assert review.correct("no-such-draft", "researcher_name", "Zhong").status_code == 404


def test_correction_file_lives_in_the_environment_workspace(review):
    review.correct("draft-r1", "researcher_name", "Zhong")
    assert review.corrections_file("draft-r1").exists()
    data = json.loads(review.corrections_file("draft-r1").read_text(encoding="utf-8"))
    assert data["draft_id"] == "draft-r1"
