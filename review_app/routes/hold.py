"""POST /drafts/<draft_id>/hold: hold a draft with a reason (Task 15.1, Requirements 5.4, 10.1, 10.2).

A hold needs a non-empty reason and a confirmed reviewer name. The reviewer
and time are written to the workspace actions log, because draft_runs has no
reviewer column for holds. A held draft never reaches growth_runs until approved.
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from review_app.effective import load_draft
from review_app.reviewers import require_confirmed_reviewer
from review_app.transaction import write_transaction
from review_app.workspace import append_action
from staging_lib.clock import later_than

blueprint = Blueprint("hold", __name__)


def refuse(message, status=400):
    return render_template("action_refused.html", message=message), status


@blueprint.route("/drafts/<draft_id>/hold", methods=["POST"])
def hold(draft_id):
    from review_app.app import get_db

    db = get_db()
    draft = load_draft(db, draft_id)
    if draft is None:
        abort(404)
    if draft.status == "Approved":
        return refuse("This draft is already approved and cannot be held.", 409)

    reason = (request.form.get("hold_reason") or "").strip()
    if not reason:
        return refuse("Give a reason for the hold.")
    page, row = (request.form.get("pdf_index") or "").strip(), (request.form.get("row") or "").strip()
    if page or row:
        if not (page.isdigit() and row.isdigit() and int(page) >= 1 and int(row) >= 1):
            return refuse("Page and row must both be whole numbers of 1 or more.")
        reason = f"{reason} (page {int(page)}, row {int(row)})"

    reviewer, response = require_confirmed_reviewer("hold this draft")
    if response is not None:
        return response

    now = later_than(draft.updated_at)
    try:
        with write_transaction(db):
            cursor = db.execute("UPDATE draft_runs SET review_status = 'Held', hold_reason = ?, updated_at = ?"
                                " WHERE draft_id = ? AND review_status <> 'Approved'", (reason, now, draft_id))
            if cursor.rowcount != 1:
                raise LookupError("approved meanwhile")
            append_action({"action": "hold", "draft_id": draft_id, "pdf_id": draft.pdf_id,
                           "reviewer": reviewer, "at": now, "hold_reason": reason})
    except LookupError:
        return refuse("This draft was approved before the hold was saved, so it was not held.", 409)
    return redirect(url_for("drafts.draft_detail", draft_id=draft_id, held=1))
