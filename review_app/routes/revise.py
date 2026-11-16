"""POST /runs/<run_id>/revise: revise an approved run (Task 19.2).

Requirements 9.1 to 9.4, 11.4, 12.1, 13.1, 29.1 to 29.5. A revision changes one
field of the latest approved values, with a reason and a confirmed reviewer
name, and must still meet every approval condition. In one transaction it
inserts revision N+1 and updates the searchable columns of the same
growth_runs row; earlier revisions are never modified. The page carries the
version it was opened at, so a revision saved meanwhile is detected (stale).
"""

from types import SimpleNamespace

from flask import Blueprint, abort, redirect, request, url_for

from review_app import approval_mapper
from review_app.corrections import CorrectionError, parse_new_value
from review_app.pdf_integrity import check_retained_copy
from review_app.preconditions import missing_verifications, unmet_conditions
from review_app.reviewers import require_confirmed_reviewer
from review_app.routes import approve as approve_routes
from review_app.routes.run_detail import render_run
from review_app.runs import latest_fields, load_run
from review_app.transaction import write_transaction
from staging_lib.clock import now_iso
from staging_lib.validate_extraction import FIELD_KEYS

blueprint = Blueprint("revise", __name__)


class StaleRevision(Exception):
    pass


def location_from_form(form, run):
    page, row = (form.get("pdf_index") or "").strip(), (form.get("row") or "").strip()
    if not page and not row:
        return run.locations[0] if run.locations else None
    if not (page.isdigit() and row.isdigit() and int(page) >= 1 and int(row) >= 1):
        raise CorrectionError("Page and row must both be whole numbers of 1 or more.")
    return {"pdf_index": int(page), "row": int(row)}


@blueprint.route("/runs/<run_id>/revise", methods=["POST"])
def revise(run_id):
    from review_app.app import get_db

    db = get_db()
    run = load_run(db, run_id)
    if run is None or run.latest is None:
        abort(404)
    form = request.form

    field_key = form.get("field")
    reason = (form.get("reason") or "").strip()
    fields = latest_fields(run)
    problems = []
    if field_key not in FIELD_KEYS:
        problems.append("Choose which field to revise.")
    if not reason:
        problems.append("Give a reason for the revision.")
    if problems:
        return render_run(run, messages=problems, status=400)

    old_value = fields[field_key]["value"]
    try:
        new_value = parse_new_value(field_key, old_value, form.get("new_value"))
        location = location_from_form(form, run)
    except CorrectionError as error:
        return render_run(run, messages=[str(error)], status=400)
    if new_value == old_value:
        return render_run(run, messages=["The new value is the same as the approved value."], status=400)

    fields[field_key]["value"] = new_value
    integrity = check_retained_copy(run.storage_path, run.file_hash)
    problems = unmet_conditions(fields, run.locations, integrity) + missing_verifications(form)
    if problems:
        return render_run(run, messages=problems, status=400)

    reviewer, response = require_confirmed_reviewer(f"save a revision of this run ({field_key.replace('_', ' ')})")
    if response is not None:
        return response

    now = now_iso()
    change = {"field": field_key, "old_value": old_value, "new_value": new_value, "reason": reason,
              "source_location": location, "reviewer": reviewer, "at": now}
    record = SimpleNamespace(draft_id=run.draft_id or run_id, pdf_id=run.pdf_id, locations=run.locations)
    columns = approval_mapper.growth_run_columns(record, fields)
    columns["run_id"] = run_id
    snapshot, _, _, _ = approval_mapper.revision_values(record, fields, [])
    changes = approval_mapper.canonical([change])
    opened_version = form.get("opened_version", "")
    try:
        with write_transaction(db):
            current = approve_routes.latest_version(db, run_id)
            if str(current) != opened_version:
                raise StaleRevision()
            approve_routes.write_growth_run(db, columns, exists=True)
            approve_routes.write_revision(db, run_id, current + 1, snapshot, changes, reviewer, now, reviewer, now)
    except StaleRevision:
        return render_run(load_run(db, run_id), stale=True, status=409)
    except Exception as error:  # rolled back; nothing saved
        return render_run(load_run(db, run_id), error=str(error), status=500)
    return redirect(url_for("runs.run_detail", run_id=run_id, revised=1))
