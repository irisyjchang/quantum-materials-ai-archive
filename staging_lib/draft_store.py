"""Draft insert, idempotent replay, and conflict detection (Task 6.2).

Requirements 3.4, 22.1, 22.2, 23.1, 23.2. Each run is stored as Pending review
with its source locations and the run entry exactly as extracted. A run whose
draft_id is already stored for the same PDF version with identical content is
skipped. Different content, or the same draft_id under another PDF version, is
a conflict and the whole batch is rolled back.
"""

import json

from staging_lib.clock import now_iso
from staging_lib.errors import Rejection


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stored_forms(run):
    """(source_locations_json, original_json) for one run entry."""
    return canonical(run["source_locations"]), canonical(run)


def stage_runs(connection, pdf_id, runs):
    """Insert new runs as Pending review. Returns the number of rows inserted. Raises Rejection on conflict."""
    inserted = 0
    for run in runs:
        draft_id = run["draft_id"]
        locations_json, original_json = stored_forms(run)
        existing = connection.execute(
            "SELECT pdf_id, source_locations_json, original_json FROM draft_runs WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json,"
                " review_status, hold_reason, updated_at) VALUES (?, ?, ?, ?, 'Pending review', NULL, ?)",
                (draft_id, pdf_id, locations_json, original_json, now_iso()),
            )
            inserted += 1
            continue
        stored_pdf_id, stored_locations, stored_original = existing
        if stored_pdf_id != pdf_id:
            raise Rejection(
                f"conflict: draft_id {draft_id!r} is already staged for another PDF version ({stored_pdf_id}); "
                "no drafts were staged"
            )
        if (stored_locations, stored_original) != (locations_json, original_json):
            raise Rejection(
                f"conflict: draft_id {draft_id!r} is already staged with different content; no drafts were staged.\n"
                f"stored:   {stored_original}\n"
                f"incoming: {original_json}"
            )
    return inserted


def mark_extraction_complete(connection, pdf_id):
    """Set extraction_complete (and clear a technical-failure reason). Returns True when the row changed."""
    status = connection.execute("SELECT status FROM processing_status WHERE pdf_id = ?", (pdf_id,)).fetchone()
    if status is not None and status[0] == "extraction_complete":
        return False
    connection.execute(
        "UPDATE processing_status SET status = 'extraction_complete', reason = NULL, updated_at = ?"
        " WHERE pdf_id = ?",
        (now_iso(), pdf_id),
    )
    return True
