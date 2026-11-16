"""Approved runs: loading, latest approved values, and the furnace layout location.

Shared by the run detail page, the revise action, and search (Tasks 19, 21, 13.6).
"""

import json
import re
from dataclasses import dataclass, field

from review_app.effective import parse_locations
from staging_lib.validate_extraction import FIELD_KEYS

_PAGE_IN_EVIDENCE = re.compile(r"\bpage\s+(\d+)\b", re.IGNORECASE)


@dataclass
class Revision:
    revision_id: str
    version: int
    approved_values: dict
    changes: list
    edited_by: object
    edited_at: object
    approved_by: str
    approved_at: str


@dataclass
class Run:
    run_id: str
    pdf_id: str
    researcher_name: object
    growth_date: object
    date_precision: object
    jc_number: object
    growth_process: object
    composition: object
    locations: list
    details: dict
    filename: str
    drive_file_id: str
    file_hash: str
    storage_path: object
    revisions: list = field(default_factory=list)

    @property
    def latest(self):
        return self.revisions[-1] if self.revisions else None

    @property
    def draft_id(self):
        latest = self.latest
        return latest.approved_values.get("draft_id") if latest else None


def _json(text, default):
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default
    return value if value is not None else default


def load_run(db, run_id):
    """Return the Run with its revisions in version order, or None."""
    row = db.execute(
        "SELECT g.run_id, g.pdf_id, g.researcher_name, g.growth_date, g.date_precision, g.jc_number,"
        " g.growth_process, g.composition_json, g.source_locations_json, g.details_json,"
        " s.archive_filename, s.drive_file_id, s.file_hash, s.storage_path"
        " FROM growth_runs AS g JOIN source_pdfs AS s ON s.pdf_id = g.pdf_id WHERE g.run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    (run_id, pdf_id, name, growth_date, precision, jc, process, composition_json, locations_json,
     details_json, filename, drive_file_id, file_hash, storage_path) = row
    run = Run(run_id, pdf_id, name, growth_date, precision, jc, process, _json(composition_json, None),
              parse_locations(locations_json), _json(details_json, {}), filename, drive_file_id, file_hash,
              storage_path)
    for values in db.execute(
        "SELECT revision_id, version, approved_values_json, changes_json, edited_by, edited_at, approved_by,"
        " approved_at FROM run_revisions WHERE run_id = ? ORDER BY version", (run_id,)
    ):
        revision_id, version, approved_json, changes_json, edited_by, edited_at, approved_by, approved_at = values
        run.revisions.append(Revision(revision_id, version, _json(approved_json, {}), _json(changes_json, []),
                                      edited_by, edited_at, approved_by, approved_at))
    return run


def latest_fields(run):
    """The latest approved values as effective-style fields (Requirement 29.1)."""
    stored = (run.latest.approved_values.get("fields") if run.latest else None) or {}
    fields = {}
    for key in FIELD_KEYS:
        value = stored.get(key) if isinstance(stored.get(key), dict) else {}
        fields[key] = {"status": value.get("status"), "raw_value": value.get("raw_value"),
                       "value": value.get("value"), "evidence": value.get("evidence"), "corrections": []}
    return fields


def layout_location(layout_field, locations):
    """Where the furnace layout sketch is (Task 13.6, Requirement 27.7).

    The page comes from the layout field's evidence when it names one
    ("PDF page 2, Furnace Layout box"), otherwise from the run's first source
    location. The row is the run's measurement-table row.
    """
    first = locations[0] if locations else {}
    page = first.get("pdf_index", 1)
    match = _PAGE_IN_EVIDENCE.search((layout_field or {}).get("evidence") or "")
    if match and int(match.group(1)) >= 1:
        page = int(match.group(1))
    return {"pdf_index": page, "row": first.get("row")}
