"""Tests for the reserved acceptance PDF guard in risk-assess (Task 4.9, Requirements 30.1 to 30.5).

Synthetic checklists with placeholder IDs only.
"""

import json

from conftest import query
from factories import PLACEHOLDER_DRIVE_ID
from staging_lib.reserved_guard import load_reserved_ids


def counts(database):
    return {
        table: query(database, f"SELECT count(*) FROM {table}")[0][0]
        for table in ("source_pdfs", "processing_status", "draft_runs")
    }


EMPTY = {"source_pdfs": 0, "processing_status": 0, "draft_runs": 0}


def test_reserved_pdf_is_refused_in_test_without_flag(workspace, capsys):
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 1
    assert "reserved for the acceptance run" in capsys.readouterr().err
    assert counts(database) == EMPTY
    assert not (workspace.root / "retained_pdfs").exists()


def test_reserved_pdf_is_accepted_with_acceptance_run_flag(workspace):
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database, acceptance_run=True) == 0
    assert counts(database)["source_pdfs"] == 1


def test_non_reserved_pdf_is_unaffected(workspace):
    workspace.reserve("placeholder-reserved-id")
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0


def test_archive_database_is_never_guarded(workspace):
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    database = workspace.database("archive")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0
    assert counts(database)["source_pdfs"] == 1


def test_missing_checklist_prints_notice_and_does_not_guard(workspace, capsys):
    database = workspace.database("test")
    assert not workspace.checklist_path.exists()
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0
    assert "No reserved acceptance list found" in capsys.readouterr().err


def test_empty_acceptance_list_behaves_like_missing(workspace, capsys):
    workspace.reserve()
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0
    assert "No reserved acceptance list found" in capsys.readouterr().err


def test_unreadable_checklist_stops_the_command(workspace):
    workspace.checklist_path.write_text("{broken", encoding="utf-8")
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 1
    assert counts(database) == EMPTY


def test_reserved_ids_ignore_blank_entries(tmp_path):
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps({"acceptance": [{"drive_file_id": " a "}, {"drive_file_id": ""}, {}]}),
                    encoding="utf-8")
    assert load_reserved_ids(path) == {"a"}
