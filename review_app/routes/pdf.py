"""GET /pdf/<pdf_id>: serve a retained source PDF (Task 13.3, Requirements 8.2, 8.3, 8.6).

Only the file recorded in source_pdfs.storage_path for that pdf_id is ever
served; no path comes from the request. A missing or changed copy is refused.
"""

from io import BytesIO
from threading import Lock

import pypdfium2 as pdfium
from flask import Blueprint, abort, current_app, render_template, request, send_file

from review_app.pdf_integrity import check_retained_copy

blueprint = Blueprint("pdf", __name__)
_render_lock = Lock()  # PDFium calls must be serialized across request threads.


def _source_row(pdf_id):
    from review_app.app import get_db

    row = get_db().execute(
        "SELECT archive_filename, storage_path, file_hash FROM source_pdfs WHERE pdf_id = ?", (pdf_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


@blueprint.route("/pdf/<pdf_id>")
def source_pdf(pdf_id):
    filename, storage_path, file_hash = _source_row(pdf_id)
    integrity = check_retained_copy(storage_path, file_hash)
    if not integrity.ok:
        return render_template("action_refused.html", message=integrity.message), 409
    return send_file(storage_path, mimetype="application/pdf", as_attachment=False,
                     download_name=filename, conditional=True)


@blueprint.route("/pdf/<pdf_id>/preview/<int:page>")
def preview_page(pdf_id, page):
    _, storage_path, file_hash = _source_row(pdf_id)
    if not check_retained_copy(storage_path, file_hash).ok:
        abort(409)

    rotation = request.args.get("rotation", default=0, type=int)
    if rotation not in (0, 90, 180, 270):
        abort(400)
    preview = BytesIO()
    try:
        with _render_lock, pdfium.PdfDocument(storage_path) as document:
            if not 1 <= page <= len(document):
                abort(404)
            source_page = document[page - 1]
            scale = min(2.5, 2000 / max(source_page.get_size()))
            bitmap = source_page.render(scale=scale, rotation=rotation)
            try:
                with bitmap.to_pil() as image:
                    image.save(preview, format="JPEG", quality=88)
            finally:
                bitmap.close()
    except (OSError, pdfium.PdfiumError, ValueError, ZeroDivisionError):
        current_app.logger.warning("Could not render PDF %s page %s", pdf_id, page, exc_info=True)
        abort(422)

    preview.seek(0)
    return send_file(preview, mimetype="image/jpeg")
