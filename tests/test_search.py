"""Tests for approved-run search (Task 21.5).

Requirements 8.2, 8.6, 10.3, 14.6, 15.1 to 15.3, 16 to 20, 19.4. Temporary databases only.
"""

import pytest

from factories import field, run
from review_app import approval_mapper
from review_app.search.ordering import ordered
from review_helpers import make_review

NONE = dict(value=None, status="missing", raw_value=None, evidence="blank cell")


def spec(draft_id, row, name, date, jc, process="unclear"):
    jc_field = field(**NONE) if jc is None else field(value=jc, raw_value=jc)
    return run(draft_id, row=row, researcher_name=field(value=name), growth_date=field(value=date),
               jc_number=jc_field, growth_process=field(value=process))


APPROVED = {
    "draft-zhong": ("Zhong", "2018-10-22", "697", "CVT"),
    "draft-alice-month": ("Alice Smith", "2018-10", None, "Flux Growth"),
    "draft-alice-day": ("alice", "2018-10-05", "06", "unclear"),
    "draft-bob": ("Bob", "2019-03-01", "697", "CVT"),
}


@pytest.fixture
def review(workspace):
    runs = [spec(draft_id, row, *values) for row, (draft_id, values) in enumerate(APPROVED.items(), 1)]
    runs += [spec("draft-pending", 5, "Zhong", "2018-10-22", "698"),
             spec("draft-held", 6, "Zhong", "2018-10-22", "699")]
    review = make_review(workspace, runs)
    for draft_id in APPROVED:
        assert review.approve(draft_id).status_code == 302
    assert review.hold("draft-held", "ratio unclear").status_code == 302
    return review


def run_id(draft_id):
    return approval_mapper.run_id_for(draft_id)


def found(review, query_string):
    page = review.client.get(f"/runs?{query_string}").get_data(as_text=True)
    ids = []
    for draft_id in list(APPROVED) + ["draft-pending", "draft-held"]:
        marker = f'data-run-id="{run_id(draft_id)}"'
        if marker in page:
            ids.append((page.index(marker), draft_id))
    return [draft_id for _, draft_id in sorted(ids)], page


# Criteria (16, 17, 18, 19) ----------------------------------------------------------------------------

def test_name_alone_is_case_insensitive_substring(review):
    assert found(review, "name=zhong")[0] == ["draft-zhong"]
    assert found(review, "name=ALI")[0] == ["draft-alice-month", "draft-alice-day"]


def test_month_alone_matches_month_only_and_day_dates_in_order(review):
    assert found(review, "month=2018-10")[0] == ["draft-alice-month", "draft-alice-day", "draft-zhong"]


def test_exact_date_matches_only_that_day(review):
    assert found(review, "date=2018-10-22")[0] == ["draft-zhong"]


def test_name_and_month_together_must_both_match(review):
    assert found(review, "name=alice&month=2018-10")[0] == ["draft-alice-month", "draft-alice-day"]
    ids, page = found(review, "name=bob&month=2018-10")
    assert ids == [] and "0 approved runs" in page


def test_jc_search_returns_every_run_sharing_the_number_with_its_source_row(review):
    ids, page = found(review, "jc=697")
    assert ids == ["draft-zhong", "draft-bob"]
    assert "page 1, row 1" in page and "page 1, row 4" in page and page.count("log-1-901.pdf") >= 2
    assert found(review, "jc=69")[0] == ["draft-zhong", "draft-bob"]


def test_partial_jc_with_leading_zero_stays_as_written(review):
    ids, page = found(review, "jc=06")
    assert ids == ["draft-alice-day"]
    assert "<td>06</td>" in page


def test_growth_process_filter(review):
    assert found(review, "process=CVT")[0] == ["draft-zhong", "draft-bob"]
    assert found(review, "process=Flux+Growth")[0] == ["draft-alice-month"]
    assert len(found(review, "process=any")[0]) == 4


def test_no_criteria_lists_every_approved_run(review):
    ids, page = found(review, "")
    assert ids == ["draft-alice-month", "draft-alice-day", "draft-zhong", "draft-bob"]
    assert "4 approved runs." in page


@pytest.mark.parametrize("bad", ["month=2018-13", "month=Oct", "date=2018-10", "process=other"])
def test_invalid_criteria_show_an_error_and_no_results(review, bad):
    ids, page = found(review, bad)
    assert ids == [] and 'class="notice"' in page


# Approved only (15, 10.3, 14.6) -----------------------------------------------------------------------

def test_pending_and_held_drafts_never_appear(review):
    for query_string in ("", "name=zhong", "month=2018-10", "date=2018-10-22", "jc=698", "jc=699"):
        ids, _ = found(review, query_string)
        assert "draft-pending" not in ids and "draft-held" not in ids


def test_approved_runs_are_searchable_while_other_drafts_from_the_pdf_are_not(review):
    status_page = review.client.get("/status").get_data(as_text=True)
    assert "4 approved · 1 pending · 1 held" in status_page
    assert len(found(review, "")[0]) == 4


def test_run_with_an_unresolved_critical_issue_does_not_appear(workspace):
    blocked = run("draft-blocked", researcher_name=field(value="Zhong"), growth_date=field(value="2018-10-22"),
                  composition=field(**NONE))
    review = make_review(workspace, [blocked])
    assert review.approve("draft-blocked").status_code == 400
    blocked_id = run_id("draft-blocked")
    for query_string in ("", "name=zhong", "month=2018-10"):
        page = review.client.get(f"/runs?{query_string}").get_data(as_text=True)
        assert blocked_id not in page and "0 approved runs" in page


# Display (17.4) ----------------------------------------------------------------------------------------

def test_month_only_date_has_no_invented_day(review):
    _, page = found(review, "name=Alice+Smith")
    assert "<td>2018-10</td>" in page and "2018-10-01" not in page


# Ordering (17.5, 20.1, 20.2) --------------------------------------------------------------------------

def result(run_id_value, date, name=None, jc=None):
    return {"run_id": run_id_value, "growth_date": date, "researcher_name": name, "jc_number": jc}


def test_same_date_without_jc_sorts_by_name_then_run_id():
    results = [result("run-3", "2018-10-22", "b"), result("run-2", "2018-10-22", "A"),
               result("run-1", "2018-10-22", "a")]
    assert [r["run_id"] for r in ordered(results)] == ["run-1", "run-2", "run-3"]


def test_same_date_and_same_jc_sorts_by_run_id():
    results = [result("run-b", "2018-10-22", "Zed", "697"), result("run-a", "2018-10-22", "Amy", "697")]
    assert [r["run_id"] for r in ordered(results)] == ["run-a", "run-b"]


def test_month_only_before_day_dates_and_missing_dates_last():
    results = [result("run-day", "2018-10-01"), result("run-none", None), result("run-month", "2018-10"),
               result("run-sept", "2018-09-30")]
    assert [r["run_id"] for r in ordered(results)] == ["run-sept", "run-month", "run-day", "run-none"]


# Open source PDF (20.3, 20.4, 8.2, 8.6) ----------------------------------------------------------------

def test_every_result_has_an_open_source_pdf_action(review):
    _, page = found(review, "")
    assert page.count(">Open source PDF</a>") == 4
    assert f'href="/runs/{run_id("draft-bob")}/source"' in page


def test_open_source_pdf_shows_the_page_and_row_label(review):
    page = review.client.get(f"/runs/{run_id('draft-bob')}/source").get_data(as_text=True)
    assert f'src="/pdf/{review.pdf_id}#page=1"' in page
    assert "page 1, row 4</strong>" in page and 'data-integrity="ok"' in page


def test_open_source_pdf_warns_about_a_tampered_copy(review):
    review.storage_path.write_bytes(b"%PDF-1.4\n% altered\n")
    page = review.client.get(f"/runs/{run_id('draft-zhong')}/source").get_data(as_text=True)
    assert 'data-integrity="mismatch"' in page and "<iframe" not in page


# JC kept as written through correction and approval (19.4) -------------------------------------------

def test_corrected_jc_with_leading_zero_is_searchable_as_written(workspace):
    review = make_review(workspace, [spec("draft-x", 1, "Zhong", "2018-10-22", "697")])
    review.correct("draft-x", "jc_number", "0697", reason="# cell reads 0697")
    review.approve("draft-x")
    ids_page = review.client.get("/runs?jc=0697").get_data(as_text=True)
    assert f'data-run-id="{run_id("draft-x")}"' in ids_page and "<td>0697</td>" in ids_page
