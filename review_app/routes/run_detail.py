"""Approved run detail, revision history, and source view (Tasks 19.1, 21.4, 13.6).

Requirements 12.1, 8.2, 8.6, 20.3, 20.4, 27.7, 29.
"""

from types import SimpleNamespace

from flask import Blueprint, abort, render_template, request

from review_app.pdf_integrity import check_retained_copy
from review_app.preconditions import VERIFICATIONS
from review_app.routes.drafts import FIELD_LABELS, edit_text, show_value
from review_app.runs import latest_fields, layout_location, load_run
from staging_lib.validate_extraction import FIELD_KEYS

blueprint = Blueprint("runs", __name__)


def selected_location(locations):
    try:
        selected = int(request.args.get("loc", 0))
    except ValueError:
        selected = 0
    return selected if 0 <= selected < len(locations) else 0


def panel_context(run):
    """Values the shared _pdf_panel.html template expects."""
    return {
        "source": SimpleNamespace(pdf_id=run.pdf_id, filename=run.filename, drive_file_id=run.drive_file_id,
                                  file_hash=run.file_hash),
        "locations": run.locations,
        "selected": selected_location(run.locations),
        "integrity": check_retained_copy(run.storage_path, run.file_hash),
    }


def render_run(run, *, status=200, **extra):
    fields = latest_fields(run)
    rows = [{"key": key, "label": FIELD_LABELS[key], "status": fields[key]["status"],
             "raw_value": fields[key]["raw_value"], "value": show_value(fields[key]["value"]),
             "edit_text": edit_text(fields[key]["value"]), "evidence": fields[key]["evidence"]}
            for key in FIELD_KEYS]
    revisions = [
        {"version": r.version, "approved_by": r.approved_by, "approved_at": r.approved_at,
         "edited_by": r.edited_by, "edited_at": r.edited_at,
         "changes": [{**c, "old_text": show_value(c.get("old_value")), "new_text": show_value(c.get("new_value"))}
                     for c in (r.changes or []) if isinstance(c, dict)]}
        for r in run.revisions
    ]
    return render_template(
        "run_detail.html", run=run, fields=rows, revisions=revisions, verifications=VERIFICATIONS,
        opened_version="" if run.latest is None else str(run.latest.version),
        layout=layout_location(fields["furnace_layout"], run.locations),
        revised=request.args.get("revised") == "1",
        **panel_context(run), **extra,
    ), status


@blueprint.route("/runs/<run_id>")
def run_detail(run_id):
    from review_app.app import get_db

    run = load_run(get_db(), run_id)
    if run is None:
        abort(404)
    return render_run(run)


@blueprint.route("/runs/<run_id>/source")
def run_source(run_id):
    """The "Open source PDF" view for a search result (Requirements 20.3, 20.4, 8.6)."""
    from review_app.app import get_db

    run = load_run(get_db(), run_id)
    if run is None:
        abort(404)
    return render_template("run_source.html", run=run, **panel_context(run))
