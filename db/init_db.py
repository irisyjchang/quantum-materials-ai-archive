"""Create an MVP database from db/schema.sql (Task 2.2).

Usage: python db/init_db.py <database.sqlite>

Refuses to touch a database that already has tables. The ``--reset`` option
for the Test environment is added in Task 22.
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connect import connect  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")


def existing_tables(path):
    if not Path(path).exists():
        return []
    connection = connect(path, read_only=True)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        connection.close()
    return [row[0] for row in rows]


def initialize(path):
    """Apply the schema to a new or empty database. Raises ValueError otherwise."""
    tables = existing_tables(path)
    if tables:
        raise ValueError(f"{path} already has tables ({', '.join(sorted(tables))}); refusing to overwrite")
    connection = connect(path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", help="path to the SQLite database to create")
    parser.add_argument("--reset", action="store_true", help="reset the Test database (Task 22)")
    args = parser.parse_args(argv)
    if args.reset:
        print("--reset is not available yet; it is added in Task 22", file=sys.stderr)
        return 1
    try:
        initialize(args.database)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Created {args.database} with the MVP schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
