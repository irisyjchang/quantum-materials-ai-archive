"""Correction store (Task 14.1, Requirements 9.2, 9.3).

Corrections made before approval are appended to
review_workspace/<environment>/corrections/<draft_id>.json. Each record holds
the field, old value, new value, reason, source location, reviewer, and time.
draft_runs.original_json is never modified.
"""

import json
import re
from datetime import date

from review_app.workspace import safe_name, workspace_dir, write_json_atomic

STRUCTURED_FIELDS = ("composition", "furnace_cycle", "furnace_layout", "timestamps", "measurements")
_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


class CorrectionError(ValueError):
    """A correction that cannot be saved; the message is shown to the reviewer."""


def corrections_path(draft_id):
    return workspace_dir() / "corrections" / f"{safe_name(draft_id)}.json"


def load_corrections(draft_id):
    path = corrections_path(draft_id)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("corrections", []))


def append_correction(draft_id, record):
    existing = load_corrections(draft_id)
    existing.append(record)
    write_json_atomic(corrections_path(draft_id), {"draft_id": draft_id, "corrections": existing})


def valid_growth_date(value):
    """True for YYYY-MM or YYYY-MM-DD naming a real month or day."""
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    year, month, *day = (int(part) for part in value.split("-"))
    try:
        date(year, month, day[0] if day else 1)
    except ValueError:
        return False
    return True


def parse_new_value(field_key, current_value, text):
    """Turn the reviewer's input into a field value, or raise CorrectionError.

    Empty input clears the value (null). Structured fields take JSON; text
    fields stay text exactly as typed, so a JC number keeps leading zeros.
    """
    text = (text or "").strip()
    if not text:
        return None
    if field_key in STRUCTURED_FIELDS and (isinstance(current_value, (dict, list)) or text[:1] in "{["):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise CorrectionError(f"The new value for {field_key} must be valid JSON: {error.msg}.") from None
        if isinstance(current_value, (dict, list)) and not isinstance(value, (dict, list)):
            raise CorrectionError(f"The new value for {field_key} must be a JSON object or list, "
                                  "like the extracted value.")
        return value
    if field_key == "growth_date" and not valid_growth_date(text):
        raise CorrectionError("The growth date must be YYYY-MM or YYYY-MM-DD, for example 2018-10 or 2018-10-22.")
    return text
