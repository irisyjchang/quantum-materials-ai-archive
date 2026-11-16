"""Filename index: archive filename to Drive file ID (Task 2.6, Requirement 1.10).

The index is a git-ignored JSON object exported from the lab's filename index,
for example {"log-1-001.pdf": "<drive file id>", ...}.
"""

import json
from pathlib import Path


class FilenameIndexError(ValueError):
    pass


def load_index(path):
    """Load and validate the index. Raises FilenameIndexError on a missing or bad file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FilenameIndexError(f"filename index not found: {path}") from None
    except json.JSONDecodeError as error:
        raise FilenameIndexError(f"filename index is not valid JSON: {path}: {error}") from None
    if not isinstance(data, dict):
        raise FilenameIndexError("filename index must be a JSON object of filename to Drive ID")
    for filename, drive_file_id in data.items():
        if not isinstance(drive_file_id, str) or not drive_file_id.strip():
            raise FilenameIndexError(f"filename index entry {filename!r} has no Drive ID")
    return data


def lookup(index, archive_filename):
    """Return the Drive ID for ``archive_filename`` (a name or a path), or None."""
    return index.get(Path(archive_filename).name)
