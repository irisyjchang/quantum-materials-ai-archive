"""Tests for check-gate (Task 5.3, Requirements 2.1, 2.2, 2.5, 6.5)."""

import hashlib
from pathlib import Path

import pytest

import staging
from conftest import query
from factories import PLACEHOLDER_DRIVE_ID

ISSUE = [{"reason": "ambiguous compound", "source_location": {"pdf_index": 1, "row": 3}}]


def check_gate(workspace, file_hash=None, drive_file_id=PLACEHOLDER_DRIVE_ID, database=None):
    return staging.main(["check-gate", drive_file_id, file_hash or workspace.pdf_hash,
                         str(database or workspace.database())])


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_non_critical_passes_and_prints_retained_path(workspace, capsys):
    workspace.risk_assess(workspace.risk_packet())
    capsys.readouterr()
    assert check_gate(workspace) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "cleared"
    retained = Path(lines[1])
    assert retained.is_absolute() and digest(retained) == workspace.pdf_hash


@pytest.mark.parametrize("decision", ["critical", "uncertain"])
def test_held_version_fails(workspace, capsys, decision):
    workspace.risk_assess(workspace.risk_packet(decision, ISSUE))
    capsys.readouterr()
    assert check_gate(workspace) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "held pending clearance" in captured.err
    assert PLACEHOLDER_DRIVE_ID in captured.err and workspace.pdf_hash in captured.err


def test_cleared_version_passes(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    query(database, "UPDATE processing_status SET status = 'cleared', clearance_by = 'Reviewer A',"
                    " clearance_at = 'now', clearance_note = 'confirmed'")
    assert check_gate(workspace) == 0


def test_unknown_version_fails(workspace, capsys):
    workspace.database()
    assert check_gate(workspace) == 1
    assert "unknown version" in capsys.readouterr().err


def test_new_hash_does_not_inherit_clearance(workspace, capsys):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    query(database, "UPDATE processing_status SET status = 'cleared', clearance_by = 'Reviewer A'")
    replacement, new_hash = workspace.make_pdf("log-1-901.pdf", b"%PDF-1.4\n% replacement\n")
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE, file_hash=new_hash), source_pdf=replacement)
    capsys.readouterr()
    assert check_gate(workspace, file_hash=new_hash) == 1
    assert "held pending clearance" in capsys.readouterr().err
    assert check_gate(workspace) == 0


def test_missing_retained_copy_fails(workspace, capsys):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet())
    Path(query(database, "SELECT storage_path FROM source_pdfs")[0][0]).unlink()
    capsys.readouterr()
    assert check_gate(workspace) == 1
    assert "retained copy is missing" in capsys.readouterr().err


def test_uppercase_hash_is_accepted(workspace):
    workspace.risk_assess(workspace.risk_packet())
    assert check_gate(workspace, file_hash=workspace.pdf_hash.upper()) == 0


def test_database_is_unchanged_by_every_call(workspace):
    database = workspace.database()
    workspace.risk_assess(workspace.risk_packet("critical", ISSUE))
    before = digest(database)
    for file_hash in (workspace.pdf_hash, "f" * 64):
        check_gate(workspace, file_hash=file_hash)
    assert digest(database) == before


def test_missing_database_fails(workspace):
    assert check_gate(workspace, database=workspace.root / "test.sqlite") == 1
    assert not (workspace.root / "test.sqlite").exists()
