"""Draft records and effective values (Task 14.3, Requirements 9.2, 9.3).

The effective value of a field is the extracted value with the reviewer's
corrections applied in order. Effective values are what the detail page shows
and what approval checks and saves. The original extraction is unchanged.
"""

import json
from dataclasses import dataclass

from review_app.corrections import load_corrections
from staging_lib.validate_extraction import FIELD_KEYS


@dataclass
class Draft:
    draft_id: str
    pdf_id: str
    status: str
    hold_reason: object
    locations: list
    original: dict
    updated_at: object
    filename: str
    drive_file_id: str
    file_hash: str
    storage_path: object


def _json(text, default):
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default


def parse_locations(text):
    data = _json(text, [])
    return [loc for loc in data if isinstance(loc, dict)] if isinstance(data, list) else []


def load_draft(db, draft_id):
    """Return the Draft, or None when it does not exist."""
    row = db.execute(
        "SELECT d.draft_id, d.pdf_id, d.review_status, d.hold_reason, d.source_locations_json, d.original_json,"
        " d.updated_at, s.archive_filename, s.drive_file_id, s.file_hash, s.storage_path"
        " FROM draft_runs AS d JOIN source_pdfs AS s ON s.pdf_id = d.pdf_id WHERE d.draft_id = ?",
        (draft_id,),
    ).fetchone()
    if row is None:
        return None
    (draft_id, pdf_id, status, hold_reason, locations_json, original_json, updated_at,
     filename, drive_file_id, file_hash, storage_path) = row
    original = _json(original_json, {})
    return Draft(draft_id, pdf_id, status, hold_reason, parse_locations(locations_json),
                 original if isinstance(original, dict) else {}, updated_at, filename, drive_file_id,
                 file_hash, storage_path)


def effective_fields(draft, corrections=None):
    """Field key -> dict with status, raw_value, value, evidence, and the corrections applied to it."""
    if corrections is None:
        corrections = load_corrections(draft.draft_id)
    stored = draft.original.get("fields", {}) if isinstance(draft.original.get("fields"), dict) else {}
    fields = {}
    for key in FIELD_KEYS:
        field = stored.get(key) if isinstance(stored.get(key), dict) else {}
        fields[key] = {
            "status": field.get("status"),
            "raw_value": field.get("raw_value"),
            "value": field.get("value"),
            "evidence": field.get("evidence"),
            "corrections": [],
        }
    for record in corrections:
        key = record.get("field")
        if key in fields:
            fields[key]["value"] = record.get("new_value")
            fields[key]["corrections"].append(record)
    return fields
