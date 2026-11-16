"""Read-only access to config.json (Task 2.4).

The lab maintains config.json by hand. No code path writes it.

- ``reviewers``: names shown in the reviewer dropdown (Requirement 7.4).
- ``backup_folder``, ``backup_name_pattern``: placeholders, null until the
  lab confirms the backup location (Requirement 26.4).
- ``checklist_path``: the Test checklist whose acceptance entries form the
  reserved list (Requirement 30.1).
- ``filename_index_path``: the index mapping archive filenames to Drive IDs
  (Requirement 1.10).

Relative paths are resolved against the project root.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"
CONFIG_ENV_VARIABLE = "GROWTH_LOG_CONFIG"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    reviewers: tuple
    backup_folder: object
    backup_name_pattern: object
    checklist_path: Path
    filename_index_path: Path


def _optional_string(data, key):
    value = data.get(key)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigError(f"{key} must be a non-empty string or null")
    return value


def _path(data, key, default, root):
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def load_config(path=None, root=PROJECT_ROOT):
    """Load and validate the config. Raises ConfigError on a bad file.

    The path defaults to $GROWTH_LOG_CONFIG when set (used by tests), else config.json.
    """
    if path is None:
        path = os.environ.get(CONFIG_ENV_VARIABLE) or CONFIG_PATH
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"config file is not valid JSON: {path}: {error}") from None
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a JSON object")

    reviewers = data.get("reviewers", [])
    if not isinstance(reviewers, list) or not all(
        isinstance(name, str) and name.strip() for name in reviewers
    ):
        raise ConfigError("reviewers must be a list of non-empty names")
    names = tuple(name.strip() for name in reviewers)
    if len(set(names)) != len(names):
        raise ConfigError("reviewers must not contain duplicate names")

    return Config(
        reviewers=names,
        backup_folder=_optional_string(data, "backup_folder"),
        backup_name_pattern=_optional_string(data, "backup_name_pattern"),
        checklist_path=_path(data, "checklist_path", "test_checklist.json", root),
        filename_index_path=_path(data, "filename_index_path", "filename_index.json", root),
    )
