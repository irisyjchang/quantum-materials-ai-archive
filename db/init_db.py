"""Create an MVP database from db/schema.sql (Task 2.2), or reset the Test environment (Task 22).

Usage:
  python db/init_db.py <database.sqlite>
  python db/init_db.py test.sqlite --reset --confirm-results-saved

Without --reset the tool refuses to touch a database that already has tables.

--reset applies to the Test environment only (Requirements 25.2, 25.5, 27.4).
It deletes and recreates test.sqlite with the MVP schema and clears the
retained_pdfs/test/ and review_workspace/test/ folders next to it. It refuses
any database not named test.sqlite, and it never touches archive.sqlite,
retained_pdfs/archive/, review_workspace/archive/, config.json, or Drive PDFs.
Because the reset deletes Test results, it also requires
--confirm-results-saved, the operator's statement that the walkthrough or
acceptance results were saved first. Stop the review app before resetting.
"""

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connect import connect  # noqa: E402
from db.env import resolve  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")
SIDE_FILE_SUFFIXES = ("-wal", "-shm", "-journal")


class ResetError(ValueError):
    """The reset was refused; nothing was deleted."""


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


@dataclass(frozen=True)
class ResetPlan:
    database_path: Path
    retained_dir: Path
    workspace_dir: Path


def plan_reset(database_path):
    """Check that ``database_path`` is a Test database and return what the reset would clear.

    Raises ResetError for anything other than a file named test.sqlite, including a
    symbolic link (which could point at archive.sqlite) or Test folders that are links.
    """
    given = Path(database_path)
    if given.name != "test.sqlite":
        raise ResetError(f"--reset only applies to the Test database test.sqlite, not {given.name}; "
                         "Archive data is never reset")
    if given.is_symlink():
        raise ResetError(f"{given} is a symbolic link; reset a real test.sqlite file only")
    database = given.absolute()
    if database.resolve().name != "test.sqlite":
        raise ResetError(f"{given} resolves to {database.resolve()}; refusing to reset it")
    environment = resolve("test", root=database.parent)
    for folder in (environment.retained_dir, environment.workspace_dir):
        if folder.is_symlink():
            raise ResetError(f"{folder} is a symbolic link; refusing to clear it")
        if folder.exists() and not folder.is_dir():
            raise ResetError(f"{folder} is not a folder; refusing to clear it")
    return ResetPlan(database, environment.retained_dir, environment.workspace_dir)


def _clear_folder(folder):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)


def reset_test(database_path, results_saved):
    """Delete and recreate test.sqlite and clear the Test retained PDFs and review workspace.

    Raises ResetError, before deleting anything, when the target is not Test or the
    operator has not confirmed that results were saved.
    """
    plan = plan_reset(database_path)
    if not results_saved:
        raise ResetError("reset refused: save the walkthrough or acceptance results first, then rerun with "
                         "--confirm-results-saved (Requirement 27.4)")
    for path in [plan.database_path] + [plan.database_path.with_name(plan.database_path.name + suffix)
                                         for suffix in SIDE_FILE_SUFFIXES]:
        if path.exists():
            path.unlink()
    _clear_folder(plan.retained_dir)
    _clear_folder(plan.workspace_dir)
    initialize(plan.database_path)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", help="path to the SQLite database to create (test.sqlite for --reset)")
    parser.add_argument("--reset", action="store_true",
                        help="delete and recreate test.sqlite and clear the Test retained PDFs and review workspace")
    parser.add_argument("--confirm-results-saved", action="store_true",
                        help="confirm that walkthrough or acceptance results were saved before the reset")
    args = parser.parse_args(argv)
    if args.reset:
        try:
            plan = reset_test(args.database, args.confirm_results_saved)
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"Reset Test: recreated {plan.database_path} with the MVP schema and cleared "
              f"{plan.retained_dir} and {plan.workspace_dir}.")
        return 0
    try:
        initialize(args.database)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Created {args.database} with the MVP schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
