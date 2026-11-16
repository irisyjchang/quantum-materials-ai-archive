"""Draft list and draft detail (Tasks 13.1, 13.2, 13.4, 14, 15.2).

Requirements 3.4, 8.1 to 8.4, 8.6, 9.2, 10.3, 10.5. The detail page shows the
effective values (extraction plus corrections) beside the source PDF, with the
correction, hold, and approval actions for drafts that are not yet approved.
"""

import json

from flask import Blueprint, abort, render_template, request

from review_app import approval_mapper
from review_app.effective import effective_fields, load_draft, parse_locations
from review_app.pdf_integrity import check_retained_copy
from review_app.runs import layout_location
from staging_lib.validate_extraction import FIELD_KEYS

blueprint = Blueprint("drafts", __name__)

FIELD_LABELS = {
    "researcher_name": "Researcher name",
    "growth_date": "Growth date",
    "jc_number": "JC number",
    "composition": "Composition (stoichiometry)",
    "furnace_cycle": "Furnace cycle",
    "furnace_layout": "Furnace layout",
    "growth_process": "Growth process",
    "timestamps": "Timestamps",
    "measurements": "Measurements",
}


def show_value(value):
    """Text for a field value: plain for strings and numbers, indented JSON for objects and lists."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return str(value)


def edit_text(value):
    """The current value as the reviewer would retype it in the correction box."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@blueprint.route("/drafts")
def draft_list():
    from review_app.app import get_db

    rows = get_db().execute(
        "SELECT d.draft_id, d.review_status, d.hold_reason, d.source_locations_json, s.archive_filename"
        " FROM draft_runs AS d JOIN source_pdfs AS s ON s.pdf_id = d.pdf_id"
        " WHERE d.review_status IN ('Pending review', 'Held')"
        " ORDER BY s.archive_filename, d.source_locations_json, d.draft_id"
    ).fetchall()
    drafts = [
        {"draft_id": draft_id, "status": status, "hold_reason": hold_reason,
         "locations": parse_locations(locations_json), "filename": filename}
        for draft_id, status, hold_reason, locations_json, filename in rows
    ]
    return render_template("drafts.html", drafts=drafts)


@blueprint.route("/drafts/<draft_id>")
def draft_detail(draft_id):
    from review_app.app import get_db

    db = get_db()
    draft = load_draft(db, draft_id)
    if draft is None:
        abort(404)
    effective = effective_fields(draft)
    fields = [
        {
            "key": key,
            "label": FIELD_LABELS[key],
            "status": effective[key]["status"],
            "raw_value": effective[key]["raw_value"],
            "value": show_value(effective[key]["value"]),
            "edit_text": edit_text(effective[key]["value"]),
            "evidence": effective[key]["evidence"],
            "corrections": effective[key]["corrections"],
        }
        for key in FIELD_KEYS
    ]
    locations = draft.locations
    try:
        selected = int(request.args.get("loc", 0))
    except ValueError:
        selected = 0
    if not 0 <= selected < len(locations):
        selected = 0

    revision = None
    if draft.status == "Approved":
        revision = db.execute(
            "SELECT version, approved_by, approved_at, edited_by FROM run_revisions WHERE run_id = ?"
            " ORDER BY version DESC LIMIT 1", (approval_mapper.run_id_for(draft_id),)
        ).fetchone()

    return render_template(
        "draft_detail.html",
        draft={"draft_id": draft.draft_id, "status": draft.status, "hold_reason": draft.hold_reason,
               "updated_at": draft.updated_at},
        source={"pdf_id": draft.pdf_id, "filename": draft.filename, "drive_file_id": draft.drive_file_id,
                "file_hash": draft.file_hash},
        fields=fields,
        locations=locations,
        selected=selected,
        integrity=check_retained_copy(draft.storage_path, draft.file_hash),
        revision=revision,
        run_id=approval_mapper.run_id_for(draft_id),
        layout=layout_location(effective["furnace_layout"], locations),
        saved=request.args.get("saved") == "1" and draft.status == "Approved",
        corrected=request.args.get("corrected"),
        held=request.args.get("held") == "1" and draft.status == "Held",
    )
