"""Local record of the last successful backup and the last failure (Task 23.1, Requirement 26.3).

One JSON file per environment at <root>/backups/status-<env>.json (git-ignored).
A failure is recorded beside the last success and never replaces it, so the
last-success timestamp only moves when a backup completes. The status view
(Task 23.4) reads the same file.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


def status_path(root, env_name):
    return Path(root) / "backups" / f"status-{env_name}.json"


@dataclass(frozen=True)
class BackupStatus:
    last_success: object  # dict with at, snapshot, destination, reason; or None
    last_failure: object  # dict with at, error, reason; or None
    unreadable: object = None  # message when the status file exists but cannot be read

    @property
    def failure_is_current(self):
        """True when the most recent recorded attempt failed."""
        if not self.last_failure:
            return False
        if not self.last_success:
            return True
        return self.last_failure.get("at", "") > self.last_success.get("at", "")


def read_status(root, env_name):
    path = status_path(root, env_name)
    if not path.exists():
        return BackupStatus(None, None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as error:
        return BackupStatus(None, None, unreadable=f"The backup status file {path} cannot be read: {error}")
    return BackupStatus(data.get("last_success"), data.get("last_failure"))


def _write(root, env_name, data):
    path = status_path(root, env_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _current(root, env_name):
    status = read_status(root, env_name)
    return {"last_success": status.last_success, "last_failure": status.last_failure}


def record_success(root, env_name, record):
    data = _current(root, env_name)
    data["last_success"] = record
    _write(root, env_name, data)


def record_failure(root, env_name, record):
    """Record a failed backup; the last-success value is left as it was."""
    data = _current(root, env_name)
    data["last_failure"] = record
    _write(root, env_name, data)
