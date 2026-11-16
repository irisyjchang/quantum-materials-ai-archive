"""Tests for the Test environment reset (Task 22.2, Requirements 25.2, 25.5, 27.4).

Every test builds its own folder under tmp_path; none opens the repository's
test.sqlite or any archive.sqlite outside tmp_path.
"""

import hashlib
import os
from pathlib import Path

import pytest

from conftest import query
from db import init_db
from db.init_db import ResetError, initialize, reset_test

TABLES = ["draft_runs", "growth_runs", "processing_status", "run_revisions", "source_pdfs"]


def digest_tree(root):
    """SHA-256 of every file under ``root`` keyed by relative path."""
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob("*")) if path.is_file()}


@pytest.fixture
def lab(tmp_path):
    """A folder laid out like the repository, with Test and Archive data and a config."""
    for name in ("test", "archive"):
        database = tmp_path / f"{name}.sqlite"
        initialize(database)
        query(database, "INSERT INTO source_pdfs VALUES (?, ?, ?, ?, ?)",
              (f"pdf-{name}", "log-1-901.pdf", f"drive-{name}", "0" * 64, None))
        retained = tmp_path / "retained_pdfs" / name
        retained.mkdir(parents=True)
        (retained / f"drive-{name}-copy.pdf").write_bytes(b"%PDF-1.4\n% " + name.encode() + b"\n")
        workspace = tmp_path / "review_workspace" / name / "corrections"
        workspace.mkdir(parents=True)
        (workspace / "draft-x.json").write_text('{"field": "jc_number"}', encoding="utf-8")
    (tmp_path / "config.json").write_text('{"reviewers": []}', encoding="utf-8")
    (tmp_path / "scans").mkdir()
    (tmp_path / "scans" / "log-1-901.pdf").write_bytes(b"%PDF-1.4\n% drive stand-in\n")
    return tmp_path


def protected(lab):
    """Everything a Test reset must leave byte-identical."""
    files = {"archive.sqlite", "config.json"}
    snapshot = {name: hashlib.sha256((lab / name).read_bytes()).hexdigest() for name in files}
    for folder in ("retained_pdfs/archive", "review_workspace/archive", "scans"):
        snapshot[folder] = digest_tree(lab / folder)
    return snapshot


def test_reset_empties_test_data_and_leaves_archive_and_config_unchanged(lab):
    before = protected(lab)
    (lab / "test.sqlite-wal").write_bytes(b"")
    reset_test(lab / "test.sqlite", results_saved=True)

    for table in TABLES:
        assert query(lab / "test.sqlite", f"SELECT count(*) FROM {table}") == [(0,)]
    assert sorted(row[0] for row in query(lab / "test.sqlite",
                  "SELECT name FROM sqlite_master WHERE type = 'table'")) == TABLES
    assert list((lab / "retained_pdfs" / "test").iterdir()) == []
    assert list((lab / "review_workspace" / "test").iterdir()) == []
    assert protected(lab) == before
    assert query(lab / "archive.sqlite", "SELECT pdf_id FROM source_pdfs") == [("pdf-archive",)]


def test_reset_creates_missing_test_folders(tmp_path):
    reset_test(tmp_path / "test.sqlite", results_saved=True)
    assert (tmp_path / "retained_pdfs" / "test").is_dir()
    assert (tmp_path / "review_workspace" / "test").is_dir()
    assert not (tmp_path / "retained_pdfs" / "archive").exists()


def test_reset_without_confirmation_is_refused_and_deletes_nothing(lab, capsys):
    before = digest_tree(lab)
    assert init_db.main([str(lab / "test.sqlite"), "--reset"]) == 1
    assert "--confirm-results-saved" in capsys.readouterr().err
    assert digest_tree(lab) == before


@pytest.mark.parametrize("name", ["archive.sqlite", "test_restore.sqlite", "Test.sqlite", "test.db"])
def test_reset_of_any_other_database_is_refused(lab, name, capsys):
    target = lab / name
    if not target.exists():
        initialize(target)
    before = digest_tree(lab)
    assert init_db.main([str(target), "--reset", "--confirm-results-saved"]) == 1
    assert "only applies to the Test database" in capsys.readouterr().err
    assert digest_tree(lab) == before


def test_symlink_named_test_sqlite_pointing_at_archive_is_refused(lab, tmp_path_factory):
    other = tmp_path_factory.mktemp("linked")
    os.symlink(lab / "archive.sqlite", other / "test.sqlite")
    before = digest_tree(lab)
    with pytest.raises(ResetError, match="symbolic link"):
        reset_test(other / "test.sqlite", results_saved=True)
    assert digest_tree(lab) == before


def test_linked_test_workspace_folder_is_refused(lab, tmp_path_factory):
    other = tmp_path_factory.mktemp("linked")
    initialize(other / "test.sqlite")
    (other / "review_workspace").mkdir()
    os.symlink(lab / "review_workspace" / "archive", other / "review_workspace" / "test")
    before = digest_tree(lab)
    with pytest.raises(ResetError, match="symbolic link"):
        reset_test(other / "test.sqlite", results_saved=True)
    assert digest_tree(lab) == before
    assert (other / "test.sqlite").exists()


def test_command_line_reset_succeeds_with_confirmation(lab, capsys):
    assert init_db.main([str(lab / "test.sqlite"), "--reset", "--confirm-results-saved"]) == 0
    assert "Reset Test" in capsys.readouterr().out
    assert query(lab / "test.sqlite", "SELECT count(*) FROM source_pdfs") == [(0,)]


def test_plain_create_still_refuses_an_existing_database(lab):
    assert init_db.main([str(lab / "test.sqlite")]) == 1
    assert query(lab / "test.sqlite", "SELECT count(*) FROM source_pdfs") == [(1,)]
