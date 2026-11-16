"""Tests for review app startup and the environment banner (Task 9.3, Requirements 25.1, 25.3, 25.4).

Every test uses temporary databases. None opens the repository's test.sqlite or archive.sqlite.
"""

import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import query
from db.env import ENV_VARIABLE
from db.init_db import initialize
from review_app.app import AppStartupError, create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root(tmp_path):
    for name in ("test", "archive"):
        initialize(tmp_path / f"{name}.sqlite")
    return tmp_path


def client(root, env_name):
    return create_app(env_name, root=root).test_client()


def add_pending_draft(database, draft_id="draft-1"):
    query(database, "INSERT OR IGNORE INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash)"
                    " VALUES ('pdf-1', 'log-1-901.pdf', 'placeholder-drive-id', 'placeholder-hash')")
    query(database, "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json, review_status)"
                    " VALUES (?, 'pdf-1', '[]', '{}', 'Pending review')", (draft_id,))


# Environment resolution (25.1, 25.3) --------------------------------------------------

def test_test_and_archive_open_their_own_databases(root):
    assert create_app("test", root=root).config["ENVIRONMENT"].database_path == root / "test.sqlite"
    assert create_app("archive", root=root).config["ENVIRONMENT"].database_path == root / "archive.sqlite"


def test_environment_variable_selects_the_environment(root, monkeypatch):
    monkeypatch.setenv(ENV_VARIABLE, "archive")
    assert create_app(root=root).config["ENVIRONMENT"].name == "archive"


def test_unknown_environment_is_refused(root):
    with pytest.raises(ValueError):
        create_app("production", root=root)


def test_missing_database_is_refused_with_setup_instruction(tmp_path):
    with pytest.raises(AppStartupError, match="python db/init_db.py test.sqlite"):
        create_app("test", root=tmp_path)
    assert not (tmp_path / "test.sqlite").exists()


def test_database_without_schema_is_refused(tmp_path):
    connection = sqlite3.connect(tmp_path / "test.sqlite")
    connection.execute("CREATE TABLE something_else (id INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(AppStartupError, match="missing the MVP tables"):
        create_app("test", root=tmp_path)


def test_test_and_archive_never_share_rows(root):
    add_pending_draft(root / "test.sqlite")
    test_page = client(root, "test").get("/").get_data(as_text=True)
    archive_page = client(root, "archive").get("/").get_data(as_text=True)
    assert "1 draft awaiting review" in test_page
    assert "0 drafts awaiting review" in archive_page
    assert query(root / "archive.sqlite", "SELECT count(*) FROM draft_runs")[0][0] == 0


def test_app_uses_foreign_keys(root):
    app = create_app("test", root=root)
    with app.app_context():
        from flask import g
        from review_app.app import get_db
        g.environment = app.config["ENVIRONMENT"]
        assert get_db().execute("PRAGMA foreign_keys").fetchone()[0] == 1


# Banner (25.4) -----------------------------------------------------------------------

@pytest.mark.parametrize("env_name, label, other", [("test", "Test", "archive"), ("archive", "Archive", "test")])
@pytest.mark.parametrize("path, status", [("/", 200), ("/no-such-page", 404)])
def test_every_page_shows_the_environment_banner(root, env_name, label, other, path, status):
    response = client(root, env_name).get(path)
    page = response.get_data(as_text=True)
    assert response.status_code == status
    assert f'data-environment="{env_name}"' in page
    assert f"<strong>{label}</strong>" in page
    assert f"env-banner-{env_name}" in page
    assert f"env-banner-{other}" not in page
    assert f"· {label}</title>" in page


def test_banner_styles_differ_for_test_and_archive():
    css = (ROOT / "review_app" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".env-banner-test" in css and ".env-banner-archive" in css


# Command line startup ------------------------------------------------------------------

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch(url, attempts=50):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.1)
    raise AssertionError(f"server did not answer at {url}")


def test_command_line_starts_in_test_on_localhost(root):
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "review_app" / "app.py"), "--env", "test", "--root", str(root),
         "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        page = fetch(f"http://127.0.0.1:{port}/")
        assert "<strong>Test</strong>" in page
        assert 'data-environment="test"' in page
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=5)
    assert f"Review app (Test) using {root / 'test.sqlite'}" in output


def test_command_line_refuses_a_missing_database(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "review_app" / "app.py"), "--env", "test", "--root", str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "database not found" in result.stderr
