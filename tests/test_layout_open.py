"""Tests for the furnace layout source-location action (Task 13.6, Requirement 27.7). Temporary databases only."""

import pytest

from factories import field, run
from review_app import approval_mapper
from review_helpers import make_review


def link(page):
    start = page.index('<p class="layout-link">')
    return page[start:page.index("</p>", start)]


@pytest.mark.parametrize("evidence, page_number", [
    ("PDF page 2, Furnace Layout box, sketch present", 2),
    ("Furnace Layout box is blank", 1),
])
def test_layout_link_on_draft_and_run_pages(workspace, evidence, page_number):
    layout = field(value={"present": True}, raw_value="sketch", evidence=evidence)
    review = make_review(workspace, [run("draft-r3", row=3, furnace_layout=layout)])
    expected = f'href="/pdf/{review.pdf_id}#page={page_number}"'

    draft_link = link(review.client.get("/drafts/draft-r3").get_data(as_text=True))
    assert expected in draft_link and 'data-row="3"' in draft_link
    assert f"page {page_number}, run on measurement-table row 3" in draft_link

    review.approve("draft-r3")
    run_page = review.client.get(f"/runs/{approval_mapper.run_id_for('draft-r3')}").get_data(as_text=True)
    run_link = link(run_page)
    assert expected in run_link and 'data-row="3"' in run_link
