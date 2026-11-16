"""Tests for backup and restore (Task 23.5, Requirements 26.1 to 26.4, 26.7).

Temporary databases and folders only; the repository's test.sqlite is never opened.
"""

import json
import os
from pathlib import Path

import pytest

from common import backup_status
from conftest import query
from db.env import resolve
from db.init_db import initialize
from review_helpers import make_review
from test_reset import digest_tree
from tools import backup, restore
from tools.backup import BackupError, NO_FOLDER_MESSAGE, take_snapshot
from tools.restore import RestoreError

TABLES = ("source_pdfs", "draft_runs", "growth_runs", "run_revisions", "processing_status")


@pytest.fixture
def lab(workspace):
    """A Test environment with one approved run, one corrected pending draft, and a retained PDF."""
    review = make_review(workspace)
    assert review.approve("draft-r1").status_code == 302
    assert review.correct("draft-r2", "jc_number", "0698", reason="JC cell reads 0698").status_code == 302
    review.client = None
    return review


@pytest.fixture
def dest(tmp_path_factory):
    return tmp_path_factory.mktemp("backups")


def rows(database, table):
    return query(database, f"SELECT * FROM {table} ORDER BY 1")


def snapshot(workspace, dest, reason="daily", extra=()):
    return backup.main(["snapshot", "--env", "test", "--dest", str(dest), "--reason", reason,
                        "--root", str(workspace.root), *extra])


def only_snapshot(dest):
    folders = [path for path in dest.iterdir() if not path.name.startswith(".")]
    assert len(folders) == 1
    return folders[0]


# Snapshot (26.1, 26.2) -------------------------------------------------------------------------------

def test_snapshot_opens_and_matches_the_source(lab, dest):
    source_before = digest_tree(lab.workspace.root / "review_workspace")
    assert snapshot(lab.workspace, dest) == 0
    folder = only_snapshot(dest)
    copy = folder / "test.sqlite"
    for table in TABLES:
        assert rows(copy, table) == rows(lab.database, table)
    assert query(copy, "PRAGMA integrity_check") == [("ok",)]
    assert query(copy, "PRAGMA journal_mode") == [("delete",)]
    assert not Path(f"{copy}-wal").exists()

    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True and manifest["problems"] == []
    assert manifest["env"] == "test" and manifest["reason"] == "daily"
    assert manifest["tables"]["growth_runs"] == 1 and manifest["tables"]["run_revisions"] == 1
    assert [entry["pdf_id"] for entry in manifest["retained_pdfs"]] == [lab.pdf_id]
    assert (folder / manifest["retained_pdfs"][0]["file"]).read_bytes() == lab.storage_path.read_bytes()
    assert digest_tree(folder / "review_workspace") == source_before
    assert (folder / "review_workspace" / "test" / "corrections" / "draft-r2.json").is_file()


def test_snapshot_leaves_the_live_environment_unchanged(lab, dest):
    before = digest_tree(lab.workspace.root / "retained_pdfs"), lab.digest()
    before_workspace = digest_tree(lab.workspace.root / "review_workspace")
    assert snapshot(lab.workspace, dest) == 0
    assert (digest_tree(lab.workspace.root / "retained_pdfs"), lab.digest()) == before
    assert digest_tree(lab.workspace.root / "review_workspace") == before_workspace


def test_pre_migration_reason_is_recorded(lab, dest):
    assert snapshot(lab.workspace, dest, reason="pre-migration") == 0
    folder = only_snapshot(dest)
    assert folder.name.endswith("-pre-migration")
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["reason"] == "pre-migration"
    status = backup_status.read_status(lab.workspace.root, "test")
    assert status.last_success["reason"] == "pre-migration"


def test_two_snapshots_in_the_same_second_get_separate_folders(lab, dest):
    assert snapshot(lab.workspace, dest) == 0
    assert snapshot(lab.workspace, dest) == 0
    names = sorted(path.name for path in dest.iterdir())
    assert len(names) == 2 and names[1].startswith(names[0])


def test_name_pattern_from_config_is_used(lab, dest):
    config = json.loads(lab.workspace.config_path.read_text(encoding="utf-8"))
    config["backup_name_pattern"] = "lab-{env}-{reason}-{timestamp}"
    lab.workspace.config_path.write_text(json.dumps(config), encoding="utf-8")
    assert snapshot(lab.workspace, dest) == 0
    assert only_snapshot(dest).name.startswith("lab-test-daily-")


def test_destination_comes_from_config_backup_folder(lab, dest):
    config = json.loads(lab.workspace.config_path.read_text(encoding="utf-8"))
    config["backup_folder"] = str(dest)
    lab.workspace.config_path.write_text(json.dumps(config), encoding="utf-8")
    assert backup.main(["snapshot", "--env", "test", "--root", str(lab.workspace.root)]) == 0
    assert only_snapshot(dest).name.startswith("growth-log-test-")


# Refusals and failures (26.3, 26.4) ------------------------------------------------------------------

def test_no_destination_is_refused_while_backup_folder_is_null(lab, capsys):
    assert backup.main(["snapshot", "--env", "test", "--root", str(lab.workspace.root)]) == 1
    message = capsys.readouterr().err
    assert "the lab has not confirmed a backup folder" in message and NO_FOLDER_MESSAGE in message
    assert not backup_status.status_path(lab.workspace.root, "test").exists()


def test_failed_backup_does_not_advance_the_last_success(lab, dest, tmp_path_factory):
    assert snapshot(lab.workspace, dest) == 0
    first = backup_status.read_status(lab.workspace.root, "test").last_success
    missing = tmp_path_factory.mktemp("gone") / "not-there"
    assert snapshot(lab.workspace, missing) == 1
    status = backup_status.read_status(lab.workspace.root, "test")
    assert status.last_success == first
    assert "backup folder not found" in status.last_failure["error"]
    assert status.failure_is_current
    assert snapshot(lab.workspace, dest) == 0
    status = backup_status.read_status(lab.workspace.root, "test")
    assert status.last_success["at"] > first["at"] and not status.failure_is_current


def test_missing_retained_pdf_keeps_an_incomplete_snapshot_and_records_failure(lab, dest, capsys):
    lab.storage_path.unlink()
    assert snapshot(lab.workspace, dest) == 1
    assert "retained copy is missing" in capsys.readouterr().err
    manifest = json.loads((only_snapshot(dest) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is False and manifest["retained_pdfs"] == []
    status = backup_status.read_status(lab.workspace.root, "test")
    assert status.last_success is None and status.failure_is_current


def test_changed_retained_pdf_is_not_copied(lab, dest):
    lab.storage_path.write_bytes(b"%PDF-1.4\n% altered\n")
    with pytest.raises(BackupError, match="no longer matches file_hash"):
        take_snapshot(resolve("test", root=lab.workspace.root), dest, "daily")
    folder = only_snapshot(dest)
    assert list((folder / "retained_pdfs" / "test").iterdir()) == []


def test_missing_database_fails_without_leaving_a_partial_folder(tmp_path, dest, workspace):
    assert snapshot(workspace, dest) == 1
    assert list(dest.iterdir()) == []
    assert backup_status.read_status(workspace.root, "test").last_failure is not None


@pytest.mark.parametrize("reason", ["", "../escape", "two words"])
def test_unsafe_reason_is_refused(lab, dest, reason):
    assert snapshot(lab.workspace, dest, reason=reason) == 1
    assert list(dest.iterdir()) == []


def test_archive_snapshot_reads_archive_only(workspace, dest):
    archive = workspace.root / "archive.sqlite"
    initialize(archive)
    before = archive.read_bytes()
    assert backup.main(["snapshot", "--env", "archive", "--dest", str(dest), "--root", str(workspace.root)]) == 0
    folder = only_snapshot(dest)
    assert (folder / "archive.sqlite").is_file() and (folder / "review_workspace" / "archive").is_dir()
    assert archive.read_bytes() == before
    assert not (workspace.root / "test.sqlite").exists()


# Restore (26.7) --------------------------------------------------------------------------------------

@pytest.fixture
def taken(lab, dest):
    assert snapshot(lab.workspace, dest) == 0
    return only_snapshot(dest)


def test_restore_into_a_separate_folder_leaves_the_source_untouched(lab, taken, tmp_path_factory):
    target = tmp_path_factory.mktemp("restored") / "drill"
    source_tree = digest_tree(lab.workspace.root)
    snapshot_tree = digest_tree(taken)
    assert restore.main([str(taken), "--target", str(target)]) == 0
    assert digest_tree(lab.workspace.root) == source_tree
    assert digest_tree(taken) == snapshot_tree

    restored = target / "test.sqlite"
    for table in ("draft_runs", "growth_runs", "run_revisions", "processing_status"):
        assert rows(restored, table) == rows(lab.database, table)
    storage = query(restored, "SELECT storage_path FROM source_pdfs")[0][0]
    assert Path(storage).parent == (target / "retained_pdfs" / "test").absolute()
    assert Path(storage).read_bytes() == lab.storage_path.read_bytes()
    assert query(lab.database, "SELECT storage_path FROM source_pdfs")[0][0] == str(lab.storage_path)
    assert (target / "review_workspace" / "test" / "corrections" / "draft-r2.json").is_file()
    report = json.loads((target / "restore_report.json").read_text(encoding="utf-8"))
    assert report["snapshot_env"] == "test" and report["storage_paths_rewritten"] == 1
    assert report["elapsed_measured_from"] == "restore_start"


def test_restore_measures_elapsed_time_from_the_report_time(taken, tmp_path):
    target = tmp_path / "drill"
    report = restore.restore(taken, target, reported_at="2026-01-01T00:00:00+00:00")
    assert report["elapsed_measured_from"] == "reported_at" and report["elapsed_seconds"] > 86400


def test_restore_refuses_an_archive_target(taken, tmp_path):
    target = tmp_path / "archive-home"
    target.mkdir()
    initialize(target / "archive.sqlite")
    before = digest_tree(target)
    assert restore.main([str(taken), "--target", str(target)]) == 1
    assert digest_tree(target) == before


def test_restore_refuses_the_live_source_folder(lab, taken):
    before = digest_tree(lab.workspace.root)
    with pytest.raises(RestoreError, match="holds live data"):
        restore.restore(taken, lab.workspace.root)
    assert digest_tree(lab.workspace.root) == before


def test_restore_refuses_the_repository(taken):
    with pytest.raises(RestoreError, match="holds live data"):
        restore.check_target(Path(__file__).resolve().parents[1], {"source_root": None})


def test_restore_refuses_a_non_empty_folder(taken, tmp_path):
    target = tmp_path / "busy"
    target.mkdir()
    (target / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RestoreError, match="not empty"):
        restore.restore(taken, target)
    assert [path.name for path in target.iterdir()] == ["notes.txt"]


def test_restore_refuses_a_symlinked_target(taken, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    os.symlink(real, tmp_path / "link")
    with pytest.raises(RestoreError, match="symbolic link"):
        restore.restore(taken, tmp_path / "link")


def test_restore_refuses_a_folder_that_is_not_a_snapshot(tmp_path):
    with pytest.raises(RestoreError, match="not a snapshot folder"):
        restore.restore(tmp_path, tmp_path / "drill")


def test_restored_workspace_opens_in_the_review_app(taken, tmp_path):
    from review_app.app import create_app

    target = tmp_path / "drill"
    restore.restore(taken, target)
    client = create_app("test", root=target).test_client()
    page = client.get("/runs").get_data(as_text=True)
    assert "1 approved run" in page
