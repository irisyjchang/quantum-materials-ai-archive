"""Print the Drive file ID for an archive filename (Task 2.6, Requirement 1.10).

Usage: python tools/lookup_drive_id.py <archive_filename> [--index PATH]

Exits 0 and prints the Drive ID when the filename is in the index. Exits 1
with a message when it is not, or when the index is missing or invalid.
The index path defaults to ``filename_index_path`` in config.json.
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import ConfigError, load_config  # noqa: E402
from common.filename_index import FilenameIndexError, load_index, lookup  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the Drive file ID for an archive filename.")
    parser.add_argument("archive_filename", help="for example log-1-042.pdf (a path is also accepted)")
    parser.add_argument("--index", help="path to the filename index (default: from config.json)")
    args = parser.parse_args(argv)
    try:
        index_path = args.index or load_config().filename_index_path
        drive_file_id = lookup(load_index(index_path), args.archive_filename)
    except (ConfigError, FilenameIndexError) as error:
        print(error, file=sys.stderr)
        return 1
    if drive_file_id is None:
        name = Path(args.archive_filename).name
        print(f"{name} is not in the filename index; add it before running the skill", file=sys.stderr)
        return 1
    print(drive_file_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
