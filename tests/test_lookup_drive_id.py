"""Tests for the filename index lookup (Task 2.6, Requirement 1.10)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from common.filename_index import FilenameIndexError, load_index, lookup

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "lookup_drive_id.py"


@pytest.fixture
def index_file(tmp_path):
    path = tmp_path / "filename_index.json"
    path.write_text(json.dumps({
        "log-1-901.pdf": "placeholder-drive-id-1",
        "log-2-902.pdf": "placeholder-drive-id-2",
    }), encoding="utf-8")
    return path


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def test_listed_filename_prints_its_id(index_file):
    result = run("log-1-901.pdf", "--index", str(index_file))
    assert result.returncode == 0
    assert result.stdout.strip() == "placeholder-drive-id-1"


def test_path_is_reduced_to_its_filename(index_file):
    result = run("/scans/binder2/log-2-902.pdf", "--index", str(index_file))
    assert result.returncode == 0
    assert result.stdout.strip() == "placeholder-drive-id-2"


def test_unlisted_filename_exits_1(index_file):
    result = run("log-1-999.pdf", "--index", str(index_file))
    assert result.returncode == 1
    assert "not in the filename index" in result.stderr
    assert result.stdout == ""


def test_missing_index_exits_1(tmp_path):
    result = run("log-1-901.pdf", "--index", str(tmp_path / "absent.json"))
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_index_entry_without_id_is_rejected(tmp_path):
    path = tmp_path / "filename_index.json"
    path.write_text(json.dumps({"log-1-901.pdf": ""}), encoding="utf-8")
    with pytest.raises(FilenameIndexError):
        load_index(path)


def test_lookup_returns_none_for_unknown(index_file):
    assert lookup(load_index(index_file), "log-1-000.pdf") is None
