"""Tests for project setup: environments, database init, and config (Task 2.5)."""

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from common.config import ConfigError, load_config
from db import env
from db.init_db import initialize

ROOT = Path(__file__).resolve().parents[1]
MVP_TABLES = {"source_pdfs", "draft_runs", "growth_runs", "run_revisions", "processing_status"}


def tables(path):
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        connection.close()


# Environments ---------------------------------------------------------------

def test_test_and_archive_resolve_to_separate_paths(tmp_path):
    test = env.resolve("test", root=tmp_path)
    archive = env.resolve("archive", root=tmp_path)
    assert test.database_path == tmp_path / "test.sqlite"
    assert archive.database_path == tmp_path / "archive.sqlite"
    assert test.retained_dir == tmp_path / "retained_pdfs" / "test"
    assert archive.retained_dir == tmp_path / "retained_pdfs" / "archive"
    assert test.workspace_dir != archive.workspace_dir
    assert test.label == "Test" and archive.label == "Archive"


def test_environment_name_is_case_insensitive(tmp_path):
    assert env.resolve(" Test ", root=tmp_path).name == "test"


def test_unknown_environment_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        env.resolve("production", root=tmp_path)


def test_environment_variable_is_used_when_no_name(tmp_path, monkeypatch):
    monkeypatch.setenv(env.ENV_VARIABLE, "archive")
    assert env.resolve(root=tmp_path).name == "archive"


def test_missing_environment_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv(env.ENV_VARIABLE, raising=False)
    with pytest.raises(ValueError):
        env.resolve(root=tmp_path)


def test_environment_for_database(tmp_path):
    assert env.environment_for_database(tmp_path / "test.sqlite") == "test"
    assert env.environment_for_database(tmp_path / "archive.sqlite") == "archive"
    assert env.environment_for_database(tmp_path / "test_restore.sqlite") is None
    assert env.environment_for_database(tmp_path / "test.db") is None


def test_retained_dir_matches_environment_layout(tmp_path):
    test = env.resolve("test", root=tmp_path)
    assert env.retained_dir_for_database(test.database_path) == test.retained_dir.resolve()


# Database init --------------------------------------------------------------

def test_init_creates_all_five_tables(tmp_path):
    database = tmp_path / "test.sqlite"
    initialize(database)
    assert tables(database) == MVP_TABLES


def test_init_refuses_existing_database(tmp_path):
    database = tmp_path / "test.sqlite"
    initialize(database)
    with pytest.raises(ValueError):
        initialize(database)


def test_init_command_line(tmp_path):
    database = tmp_path / "cli.sqlite"
    result = subprocess.run(
        [sys.executable, str(ROOT / "db" / "init_db.py"), str(database)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert tables(database) == MVP_TABLES
    again = subprocess.run(
        [sys.executable, str(ROOT / "db" / "init_db.py"), str(database)],
        capture_output=True, text=True,
    )
    assert again.returncode == 1
    assert "already has tables" in again.stderr


# Config ---------------------------------------------------------------------

def write_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_project_config_loads():
    config = load_config()
    assert config.backup_folder is None
    assert config.backup_name_pattern is None
    assert config.checklist_path == ROOT / "test_checklist.local.json"
    assert config.filename_index_path == ROOT / "filename_index.json"


def test_config_reads_reviewers_and_resolves_paths(tmp_path):
    path = write_config(tmp_path, {
        "reviewers": ["Reviewer A", "Reviewer B"],
        "checklist_path": "lists/checklist.json",
        "filename_index_path": "index.json",
    })
    config = load_config(path, root=tmp_path)
    assert config.reviewers == ("Reviewer A", "Reviewer B")
    assert config.checklist_path == tmp_path / "lists" / "checklist.json"
    assert config.filename_index_path == tmp_path / "index.json"


@pytest.mark.parametrize("reviewers", [["A", "A"], ["A", ""], "A", [1]])
def test_bad_reviewer_lists_are_rejected(tmp_path, reviewers):
    path = write_config(tmp_path, {"reviewers": reviewers})
    with pytest.raises(ConfigError):
        load_config(path, root=tmp_path)


def test_missing_config_is_reported(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.json", root=tmp_path)


def test_config_is_read_only():
    before = (ROOT / "config.json").read_bytes()
    load_config()
    assert (ROOT / "config.json").read_bytes() == before


# Pilot isolation ------------------------------------------------------------

def test_mvp_code_does_not_import_pilot():
    pattern = re.compile(r"^\s*(from|import)\s+pilot\b", re.MULTILINE)
    offenders = []
    for folder in ("db", "common", "staging_lib", "review_app", "tools"):
        for source in (ROOT / folder).rglob("*.py"):
            if pattern.search(source.read_text(encoding="utf-8")):
                offenders.append(str(source.relative_to(ROOT)))
    assert offenders == []
