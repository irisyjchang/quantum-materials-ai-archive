"""Files in the environment's review workspace (git-ignored).

- corrections/<draft_id>.json: corrections made before approval (Task 14)
- actions.jsonl: an append-only log of recorded actions that have no reviewer
  column in the database, such as holds (Requirement 7)

Writes go through a temporary file and an atomic rename, so a reader never
sees a half-written file.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from flask import current_app

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def workspace_dir():
    return Path(current_app.config["ENVIRONMENT"].workspace_dir)


def safe_name(identifier):
    """A file name for an identifier; unusual identifiers are hashed so they cannot escape the folder."""
    if _SAFE.match(identifier) and identifier not in (".", ".."):
        return identifier
    return "id-" + hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:32]


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def append_action(record):
    """Append one recorded action to actions.jsonl."""
    path = workspace_dir() / "actions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
