"""GET /status: the processing status view (Task 11, Requirements 14.1 to 14.5, 14.7, 10.4, 30.6)."""

from flask import Blueprint, current_app, render_template, request

from review_app.queries.status import pdf_statuses
from staging_lib.reserved_guard import ReservedListError, load_reserved_ids

blueprint = Blueprint("status", __name__)


def reserved_ids_for_view(environment, checklist_path):
    """(reserved drive_file_ids, warning). Labels appear in Test only (Requirement 30.6)."""
    if environment.name != "test":
        return frozenset(), None
    try:
        return frozenset(load_reserved_ids(checklist_path) or ()), None
    except ReservedListError as error:
        return frozenset(), f"Reserved acceptance PDFs cannot be labelled: {error}"


@blueprint.route("/status")
def status():
    from review_app.app import get_db

    environment = current_app.config["ENVIRONMENT"]
    reserved, warning = reserved_ids_for_view(environment, current_app.config["CHECKLIST_PATH"])
    rows = pdf_statuses(get_db(), reserved)
    cleared_id = request.args.get("cleared")
    cleared_row = next((row for row in rows if row.pdf_id == cleared_id and row.status == "cleared"), None)
    return render_template("status.html", rows=rows, reserved_warning=warning, cleared_row=cleared_row)
