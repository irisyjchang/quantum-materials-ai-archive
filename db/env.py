"""Resolve the Test or Archive environment to its paths (Task 2.3).

Test and Archive use the same code and schema with separate databases,
retained-PDF directories, and review workspaces.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_VARIABLE = "GROWTH_LOG_ENV"
ENVIRONMENTS = ("test", "archive")


@dataclass(frozen=True)
class Environment:
    name: str
    database_path: Path
    retained_dir: Path
    workspace_dir: Path

    @property
    def label(self):
        return self.name.capitalize()


def resolve(name=None, root=PROJECT_ROOT):
    """Return the Environment for ``name``, or for $GROWTH_LOG_ENV if ``name`` is None."""
    if name is None:
        name = os.environ.get(ENV_VARIABLE)
    if not name:
        raise ValueError(f"no environment given; pass --env or set {ENV_VARIABLE} to test or archive")
    name = name.strip().lower()
    if name not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {name!r}; use test or archive")
    root = Path(root)
    return Environment(
        name=name,
        database_path=root / f"{name}.sqlite",
        retained_dir=root / "retained_pdfs" / name,
        workspace_dir=root / "review_workspace" / name,
    )


def environment_for_database(database_path):
    """Return ``"test"`` or ``"archive"`` for a database named test.sqlite or archive.sqlite, else None.

    The environment is identified by the database file name, so checks that
    apply to one environment only (such as the reserved acceptance PDF guard,
    which applies to the Test database) work wherever the file lives.
    """
    path = Path(database_path)
    if path.suffix == ".sqlite" and path.stem in ENVIRONMENTS:
        return path.stem
    return None


def retained_dir_for_database(database_path):
    """Directory for retained PDF copies that belong to ``database_path``.

    For test.sqlite and archive.sqlite in the project root this is
    retained_pdfs/test/ and retained_pdfs/archive/, matching ``resolve``.
    """
    path = Path(database_path).resolve()
    return path.parent / "retained_pdfs" / path.stem
