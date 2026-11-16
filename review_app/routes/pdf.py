"""GET /pdf/<pdf_id>: serve a retained source PDF (Task 13.3, Requirements 8.2, 8.3, 8.6).

Only the file recorded in source_pdfs.storage_path for that pdf_id is ever
served; no path comes from the request. A missing or changed copy is refused.
"""

from flask import Blueprint, abort, render_template, send_file

from review_app.pdf_integrity import check_retained_copy

blueprint = Blueprint("pdf", __name__)


@blueprint.route("/pdf/<pdf_id>")
def source_pdf(pdf_id):
    from review_app.app import get_db

    row = get_db().execute(
        "SELECT archive_filename, storage_path, file_hash FROM source_pdfs WHERE pdf_id = ?", (pdf_id,)
    ).fetchone()
    if row is None:
        abort(404)
    filename, storage_path, file_hash = row
    integrity = check_retained_copy(storage_path, file_hash)
    if not integrity.ok:
        return render_template("action_refused.html", message=integrity.message), 409
    return send_file(storage_path, mimetype="application/pdf", as_attachment=False,
                     download_name=filename, conditional=True)
