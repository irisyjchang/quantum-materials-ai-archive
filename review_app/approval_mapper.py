"""Map effective values to the approved records (Task 17.1, Requirement 12.1).

Builds the searchable growth_runs columns and the run_revisions snapshot.
run_id is derived from draft_id, so a retried approval is detectable.
"""

import hashlib
import json

GROWTH_PROCESSES = {"cvt": "CVT", "flux": "Flux Growth", "flux growth": "Flux Growth", "unclear": "unclear"}
DETAIL_FIELDS = ("furnace_cycle", "furnace_layout", "growth_process", "timestamps", "measurements")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def run_id_for(draft_id):
    return "run-" + hashlib.sha256(draft_id.encode("utf-8")).hexdigest()[:20]


def revision_id_for(run_id, version):
    return f"{run_id}-v{version}"


def _text(value):
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value)
    return text or None


def jc_number(field):
    """The JC number as text exactly as written (Requirement 19.4); never converted to a number."""
    value = field["value"]
    if isinstance(value, str):
        return _text(value)
    if isinstance(field["raw_value"], str) and field["raw_value"].strip():
        return field["raw_value"].strip()
    return _text(value)


def growth_process(field):
    value = field["value"]
    if isinstance(value, str):
        return GROWTH_PROCESSES.get(value.strip().lower())
    return None


def growth_run_columns(draft, fields):
    date_value = _text(fields["growth_date"]["value"])
    return {
        "run_id": run_id_for(draft.draft_id),
        "pdf_id": draft.pdf_id,
        "researcher_name": _text(fields["researcher_name"]["value"]),
        "growth_date": date_value,
        "date_precision": None if date_value is None else ("day" if len(date_value) == 10 else "month"),
        "jc_number": jc_number(fields["jc_number"]),
        "growth_process": growth_process(fields["growth_process"]),
        "composition_json": canonical(fields["composition"]["value"]),
        "source_locations_json": canonical(draft.locations),
        "details_json": canonical({
            key: {part: fields[key][part] for part in ("status", "raw_value", "value", "evidence")}
            for key in DETAIL_FIELDS
        }),
    }


def revision_values(draft, fields, corrections):
    """(approved_values_json, changes_json, edited_by, edited_at)."""
    snapshot = {
        "draft_id": draft.draft_id,
        "source_locations": draft.locations,
        "fields": {key: {part: field[part] for part in ("status", "raw_value", "value", "evidence")}
                   for key, field in fields.items()},
    }
    if not corrections:
        return canonical(snapshot), None, None, None
    editors = []
    for record in corrections:
        if record["reviewer"] not in editors:
            editors.append(record["reviewer"])
    return canonical(snapshot), canonical(corrections), ", ".join(editors), corrections[-1]["at"]
