"""POST /status/<pdf_id>/clear: reviewer clearance of a held PDF (Task 12.1).

Requirements 6.2, 6.3, 6.5, 1.6, 7.1 to 7.3. Clearance applies only to the
exact PDF version (pdf_id) that is currently held pending clearance, so a
replacement version is never cleared by an older version's clearance.
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from review_app.reviewers import require_confirmed_reviewer
from staging_lib.clock import now_iso

blueprint = Blueprint("clearance", __name__)


def refuse(message, status):
    return render_template("action_refused.html", message=message), status


@blueprint.route("/status/<pdf_id>/clear", methods=["POST"])
def clear(pdf_id):
    from review_app.app import get_db

    db = get_db()
    row = db.execute(
        "SELECT s.archive_filename, p.status FROM source_pdfs AS s"
        " JOIN processing_status AS p ON p.pdf_id = s.pdf_id WHERE s.pdf_id = ?",
        (pdf_id,),
    ).fetchone()
    if row is None:
        abort(404)
    filename, status = row
    if status != "held_pending_clearance":
        return refuse(f"{filename} is not held pending clearance, so there is nothing to clear.", 409)

    note = (request.form.get("clearance_note") or "").strip()
    if not note:
        return refuse("Write a clearance note explaining how the issue was resolved.", 400)

    reviewer, response = require_confirmed_reviewer(f"clear {filename} for extraction")
    if response is not None:
        return response

    db.isolation_level = None
    db.execute("BEGIN IMMEDIATE")
    try:
        cursor = db.execute(
            "UPDATE processing_status SET status = 'cleared', clearance_by = ?, clearance_at = ?,"
            " clearance_note = ?, reason = NULL, updated_at = ?"
            " WHERE pdf_id = ? AND status = 'held_pending_clearance'",
            (reviewer, now_iso(), note, now_iso(), pdf_id),
        )
        if cursor.rowcount != 1:
            db.execute("ROLLBACK")
            return refuse(f"{filename} changed before the clearance was saved; reload the status page.", 409)
        db.execute("COMMIT")
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    return redirect(url_for("status.status", cleared=pdf_id))
