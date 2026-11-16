"""Extraction packet validation (Task 3.3, Requirement 21.5)."""

FIELD_KEYS = (
    "researcher_name",
    "growth_date",
    "jc_number",
    "composition",
    "furnace_cycle",
    "furnace_layout",
    "growth_process",
    "timestamps",
    "measurements",
)
FIELD_STATUSES = ("recorded", "inferred", "derived", "missing", "unreadable", "ambiguous", "omitted")
FIELD_PARTS = ("status", "raw_value", "value", "evidence")


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _validate_locations(label, locations):
    if not isinstance(locations, list) or not locations:
        return f"{label}: source_locations must be a non-empty array"
    for number, location in enumerate(locations, 1):
        if not isinstance(location, dict):
            return f"{label}: source location {number} must be an object"
        for key in ("pdf_index", "row"):
            if not _is_positive_integer(location.get(key)):
                return f"{label}: source location {number} needs {key} as an integer of 1 or more"
    return None


def _validate_fields(label, fields):
    if not isinstance(fields, dict):
        return f"{label}: fields must be an object"
    missing = [key for key in FIELD_KEYS if key not in fields]
    if missing:
        return f"{label}: fields is missing {', '.join(missing)}"
    extra = sorted(set(fields) - set(FIELD_KEYS))
    if extra:
        return f"{label}: fields has unknown keys {', '.join(extra)}"
    for key in FIELD_KEYS:
        field = fields[key]
        if not isinstance(field, dict):
            return f"{label}.{key} must be an object"
        absent = [part for part in FIELD_PARTS if part not in field]
        if absent:
            return f"{label}.{key} is missing {', '.join(absent)}"
        if field["status"] not in FIELD_STATUSES:
            return f"{label}.{key} has invalid status {field['status']!r}"
        if field["raw_value"] is not None and not isinstance(field["raw_value"], str):
            return f"{label}.{key} raw_value must be text as written, or null"
        evidence = field["evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            return f"{label}.{key} needs evidence (a source location or why the value is unavailable)"
    return None


def validate_extraction(packet):
    """Return a descriptive error string, or None when the extraction fields are valid."""
    runs = packet.get("runs")
    if not isinstance(runs, list):
        return "runs must be an array"
    if not runs:
        return "runs is empty; an extraction packet must contain at least one run"
    seen = set()
    for number, run in enumerate(runs, 1):
        label = f"run {number}"
        if not isinstance(run, dict):
            return f"{label} must be an object"
        draft_id = run.get("draft_id")
        if not isinstance(draft_id, str) or not draft_id.strip():
            return f"{label} needs a non-empty draft_id"
        if draft_id in seen:
            return f"draft_id {draft_id!r} appears more than once in the packet"
        seen.add(draft_id)
        label = f"run {draft_id}"
        error = _validate_locations(label, run.get("source_locations"))
        if error:
            return error
        error = _validate_fields(label, run.get("fields"))
        if error:
            return error
    return None
