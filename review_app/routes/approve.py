"""Approval page and atomic approval (Tasks 16.2, 17, 18).

Requirements 7.2, 8.6, 11.1 to 11.4, 12.1 to 12.4, 13.1, 13.2.

GET shows unmet conditions (approve disabled) or the approval form. POST
re-checks every condition, asks the reviewer to confirm their name, then in
one BEGIN IMMEDIATE transaction:

1. returns the saved revision if this approval already committed (retry),
2. refuses a stale page (draft updated_at or revision version changed),
3. writes growth_runs, run_revisions, and the Approved status together.

"Saved" is shown only after the commit. Any failure rolls back everything.
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from review_app import approval_mapper
from review_app.corrections import load_corrections
from review_app.effective import effective_fields, load_draft
from review_app.pdf_integrity import check_retained_copy
from review_app.preconditions import VERIFICATIONS, missing_verifications, unmet_conditions
from review_app.reviewers import require_confirmed_reviewer
from review_app.routes.drafts import FIELD_LABELS, show_value
from review_app.transaction import write_transaction
from staging_lib.clock import later_than, now_iso

blueprint = Blueprint("approve", __name__)


class StaleApproval(Exception):
    """The draft or run changed after the reviewer opened the page."""


def latest_version(db, run_id):
    row = db.execute("SELECT max(version) FROM run_revisions WHERE run_id = ?", (run_id,)).fetchone()
    return row[0]


def opened_state(db, draft):
    """What the reviewer sees when the page is opened: updated_at, plus version only if a revision exists."""
    version = latest_version(db, approval_mapper.run_id_for(draft.draft_id))
    return {"opened_updated_at": draft.updated_at or "", "opened_version": "" if version is None else str(version)}


def render_page(db, draft, *, messages=(), stale=False, error=None, status=200):
    fields = effective_fields(draft)
    integrity = check_retained_copy(draft.storage_path, draft.file_hash)
    unmet = unmet_conditions(fields, draft.locations, integrity)
    summary = [(FIELD_LABELS[key], show_value(fields[key]["value"]))
               for key in ("researcher_name", "growth_date", "jc_number", "composition")]
    return render_template(
        "approve.html", draft=draft, summary=summary, unmet=unmet, messages=list(messages), stale=stale,
        error=error, verifications=VERIFICATIONS, state=opened_state(db, draft),
    ), status


# Write steps, kept separate so a test can inject a failure between them.

def write_growth_run(db, columns, exists):
    if exists:
        db.execute(
            "UPDATE growth_runs SET pdf_id = :pdf_id, researcher_name = :researcher_name,"
            " growth_date = :growth_date, date_precision = :date_precision, jc_number = :jc_number,"
            " growth_process = :growth_process, composition_json = :composition_json,"
            " source_locations_json = :source_locations_json, details_json = :details_json"
            " WHERE run_id = :run_id", columns)
    else:
        db.execute(
            "INSERT INTO growth_runs (run_id, pdf_id, researcher_name, growth_date, date_precision, jc_number,"
            " growth_process, composition_json, source_locations_json, details_json) VALUES (:run_id, :pdf_id,"
            " :researcher_name, :growth_date, :date_precision, :jc_number, :growth_process, :composition_json,"
            " :source_locations_json, :details_json)", columns)


def write_revision(db, run_id, version, snapshot, changes, edited_by, edited_at, reviewer, approved_at):
    db.execute(
        "INSERT INTO run_revisions (revision_id, run_id, version, approved_values_json, changes_json, edited_by,"
        " edited_at, approved_by, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (approval_mapper.revision_id_for(run_id, version), run_id, version, snapshot, changes, edited_by,
         edited_at, reviewer, approved_at))


def mark_approved(db, draft_id, approved_at):
    db.execute("UPDATE draft_runs SET review_status = 'Approved', hold_reason = NULL, updated_at = ?"
               " WHERE draft_id = ?", (approved_at, draft_id))


@blueprint.route("/drafts/<draft_id>/approve", methods=["GET"])
def approve_page(draft_id):
    from review_app.app import get_db

    db = get_db()
    draft = load_draft(db, draft_id)
    if draft is None:
        abort(404)
    if draft.status == "Approved":
        return redirect(url_for("drafts.draft_detail", draft_id=draft_id))
    return render_page(db, draft)


@blueprint.route("/drafts/<draft_id>/approve", methods=["POST"])
def approve(draft_id):
    from review_app.app import get_db

    db = get_db()
    draft = load_draft(db, draft_id)
    if draft is None:
        abort(404)
    form = request.form
    run_id = approval_mapper.run_id_for(draft_id)
    opened_version = form.get("opened_version", "")
    expected_version = int(opened_version) + 1 if opened_version.isdigit() else 1

    # Retry of an approval that already committed (Requirement 12.4).
    if draft.status == "Approved":
        if (latest_version(db, run_id) or 0) >= expected_version:
            return redirect(url_for("drafts.draft_detail", draft_id=draft_id, saved=1))
        return render_page(db, draft, stale=True, status=409)

    # Conditions are re-checked on every submit; a forged POST cannot skip them (Requirement 11.4).
    fields = effective_fields(draft)
    integrity = check_retained_copy(draft.storage_path, draft.file_hash)
    problems = unmet_conditions(fields, draft.locations, integrity) + missing_verifications(form)
    if problems:
        return render_page(db, draft, messages=problems, status=400)

    reviewer, response = require_confirmed_reviewer("approve this draft and add it to the archive search")
    if response is not None:
        return response

    corrections = load_corrections(draft_id)
    fields = effective_fields(draft, corrections)
    columns = approval_mapper.growth_run_columns(draft, fields)
    snapshot, changes, edited_by, edited_at = approval_mapper.revision_values(draft, fields, corrections)
    approved_at = now_iso()
    try:
        with write_transaction(db):
            current = db.execute("SELECT review_status, updated_at FROM draft_runs WHERE draft_id = ?",
                                 (draft_id,)).fetchone()
            version_now = latest_version(db, run_id)
            if current[0] == "Approved" and (version_now or 0) >= expected_version:
                raise StaleApproval("already saved")
            # Stale-approval protection (Requirements 13.1, 13.2).
            if (current[1] or "") != form.get("opened_updated_at", ""):
                raise StaleApproval("draft changed")
            if version_now is not None and str(version_now) != opened_version:
                raise StaleApproval("revision changed")
            exists = db.execute("SELECT 1 FROM growth_runs WHERE run_id = ?", (run_id,)).fetchone() is not None
            write_growth_run(db, columns, exists)
            write_revision(db, run_id, (version_now or 0) + 1, snapshot, changes, edited_by, edited_at,
                           reviewer, approved_at)
            mark_approved(db, draft_id, later_than(current[1]))
    except StaleApproval as error:
        if str(error) == "already saved":
            return redirect(url_for("drafts.draft_detail", draft_id=draft_id, saved=1))
        return render_page(db, load_draft(db, draft_id), stale=True, status=409)
    except Exception as error:  # rolled back by write_transaction; nothing was saved
        return render_page(db, load_draft(db, draft_id), error=str(error), status=500)
    return redirect(url_for("drafts.draft_detail", draft_id=draft_id, saved=1))
