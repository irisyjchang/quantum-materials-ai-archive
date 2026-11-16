"""POST /drafts/<draft_id>/correct: correct one field (Task 14.2, Requirements 7.1, 9.1 to 9.4).

Requires a reason and a confirmed reviewer name. The correction is appended to
the workspace file and draft_runs.updated_at is bumped in the same transaction,
so a stale approval page is caught (Requirement 13). original_json is unchanged.
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from review_app.corrections import CorrectionError, append_correction, parse_new_value
from review_app.effective import effective_fields, load_draft
from review_app.reviewers import require_confirmed_reviewer
from review_app.transaction import write_transaction
from staging_lib.clock import later_than
from staging_lib.validate_extraction import FIELD_KEYS

blueprint = Blueprint("corrections", __name__)


def refuse(message, status=400):
    return render_template("action_refused.html", message=message), status


def location_from_form(form, draft):
    """The source location the correction refers to: the submitted page and row, else the draft's first."""
    page, row = (form.get("pdf_index") or "").strip(), (form.get("row") or "").strip()
    if not page and not row:
        return draft.locations[0] if draft.locations else None
    try:
        location = {"pdf_index": int(page), "row": int(row)}
    except ValueError:
        raise CorrectionError("Page and row must both be whole numbers of 1 or more.") from None
    if location["pdf_index"] < 1 or location["row"] < 1:
        raise CorrectionError("Page and row must both be whole numbers of 1 or more.")
    return location


@blueprint.route("/drafts/<draft_id>/correct", methods=["POST"])
def correct(draft_id):
    from review_app.app import get_db

    db = get_db()
    draft = load_draft(db, draft_id)
    if draft is None:
        abort(404)
    if draft.status == "Approved":
        return refuse("This draft is already approved. Corrections to an approved run go through a revision.", 409)

    form = request.form
    field_key = form.get("field")
    if field_key not in FIELD_KEYS:
        return refuse("Choose which field to correct.")
    reason = (form.get("reason") or "").strip()
    if not reason:
        return refuse("Give a reason for the correction.")
    fields = effective_fields(draft)
    old_value = fields[field_key]["value"]
    try:
        new_value = parse_new_value(field_key, old_value, form.get("new_value"))
        location = location_from_form(form, draft)
    except CorrectionError as error:
        return refuse(str(error))
    if new_value == old_value:
        return refuse("The new value is the same as the current value, so there is nothing to correct.")

    reviewer, response = require_confirmed_reviewer(f"correct {field_key.replace('_', ' ')} on this draft")
    if response is not None:
        return response

    now = later_than(draft.updated_at)
    record = {"field": field_key, "old_value": old_value, "new_value": new_value, "reason": reason,
              "source_location": location, "reviewer": reviewer, "at": now}
    with write_transaction(db):
        db.execute("UPDATE draft_runs SET updated_at = ? WHERE draft_id = ?", (now, draft_id))
        append_correction(draft_id, record)
    return redirect(url_for("drafts.draft_detail", draft_id=draft_id, corrected=field_key))
