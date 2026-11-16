"""Reserved acceptance PDF guard (Task 4.8, Requirements 30.1 to 30.5).

In the Test database, risk-assess and stage-drafts refuse a PDF whose
drive_file_id is on the reserved acceptance list unless --acceptance-run is
given. The guard never applies to the Archive database or to check-gate.

It prevents mistakes, not misuse: it does not stop the skill from reading a
scan in Codex, and anyone who passes --acceptance-run can bypass it.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from db.env import environment_for_database


class ReservedListError(ValueError):
    pass


@dataclass(frozen=True)
class GuardResult:
    error: object = None   # message when the PDF must be refused
    notice: object = None  # informational message to print


def load_reserved_ids(checklist_path):
    """Return the set of reserved drive_file_ids, or None when there is no reserved list."""
    path = Path(checklist_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReservedListError(f"checklist could not be read: {path}: {error}") from None
    if not isinstance(data, dict):
        raise ReservedListError(f"checklist must be a JSON object: {path}")
    entries = data.get("acceptance") or []
    if not isinstance(entries, list):
        raise ReservedListError(f"checklist acceptance must be a list: {path}")
    ids = {
        entry["drive_file_id"].strip()
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("drive_file_id"), str)
        and entry["drive_file_id"].strip()
    }
    return ids or None


def check(database_path, drive_file_id, acceptance_run, checklist_path):
    """Decide whether this command may process ``drive_file_id``. Raises ReservedListError."""
    if environment_for_database(database_path) != "test" or acceptance_run:
        return GuardResult()
    reserved = load_reserved_ids(checklist_path)
    if reserved is None:
        return GuardResult(notice=f"No reserved acceptance list found at {checklist_path}; reserved-PDF guard not applied.")
    if drive_file_id in reserved:
        return GuardResult(error=(
            f"{drive_file_id} is reserved for the acceptance run; nothing was recorded. "
            "Use a non-reserved PDF for the walkthrough, or pass --acceptance-run during the acceptance run."
        ))
    return GuardResult()
