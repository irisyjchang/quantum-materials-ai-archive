"""Tests for stage-drafts (Tasks 6.5, 6.3, 6.9).

Requirements 2.3, 2.4, 3.4, 3.5, 4.3, 5.3, 14.7, 14.8, 21.3, 21.6, 22.1, 22.2,
23.1, 23.2, 24.2, 30.2 to 30.4.
"""

import hashlib
import json
from pathlib import Path

import staging
from conftest import query
from factories import PLACEHOLDER_DRIVE_ID, field, run
from staging_lib import draft_store, status_store

ISSUE = [{"reason": "ambiguous ratio", "source_location": {"pdf_index": 1, "row": 2}}]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def drafts(database):
    return query(database, "SELECT draft_id, pdf_id, source_locations_json, original_json, review_status,"
                           " hold_reason FROM draft_runs ORDER BY draft_id")


def status(database):
    return query(database, "SELECT status, reason FROM processing_status")[0]


def assessed(workspace, decision="non_critical", issues=None):
    database = workspace.database()
    assert workspace.risk_assess(workspace.risk_packet(decision, issues)) == 0
    return database


def two_runs():
    return [run("draft-p1-r1", row=1), run("draft-p1-r2", row=2)]


# Successful staging -------------------------------------------------------------

def test_non_critical_version_stages_pending_drafts(workspace, capsys):
    database = assessed(workspace)
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet(two_runs())) == 0
    rows = drafts(database)
    assert [row[0] for row in rows] == ["draft-p1-r1", "draft-p1-r2"]
    assert {row[4] for row in rows} == {"Pending review"}
    assert json.loads(rows[1][2]) == [{"pdf_index": 1, "row": 2}]
    assert json.loads(rows[0][3])["fields"]["jc_number"]["raw_value"] == "JC1302"
    assert status(database) == ("extraction_complete", None)
    assert "2 rows staged as Pending review" in capsys.readouterr().out


def test_lower_table_issues_do_not_need_clearance(workspace):
    lower_table_issue = [{"reason": "smudged entry in the lower table", "source_location": {"pdf_index": 1, "row": 9}}]
    database = assessed(workspace, "non_critical", lower_table_issue)
    assert workspace.stage_drafts(workspace.extraction_packet()) == 0
    assert len(drafts(database)) == 1


def test_cleared_version_can_be_staged(workspace):
    database = assessed(workspace, "critical", ISSUE)
    query(database, "UPDATE processing_status SET status = 'cleared', clearance_by = 'Reviewer A',"
                    " clearance_at = 'now', clearance_note = 'basis confirmed'")
    assert workspace.stage_drafts(workspace.extraction_packet()) == 0
    assert status(database)[0] == "extraction_complete"


# Rejections write nothing --------------------------------------------------------

def test_unknown_version_is_rejected(workspace, capsys):
    database = workspace.database()
    before = digest(database)
    assert workspace.stage_drafts(workspace.extraction_packet()) == 1
    assert "risk-assess must complete" in capsys.readouterr().err
    assert drafts(database) == []
    assert digest(database) == before


def test_held_version_is_rejected_with_zero_drafts(workspace, capsys):
    database = assessed(workspace, "uncertain", ISSUE)
    capsys.readouterr()
    before = digest(database)
    assert workspace.stage_drafts(workspace.extraction_packet()) == 1
    error = capsys.readouterr().err
    assert "extraction gate failed" in error and PLACEHOLDER_DRIVE_ID in error and workspace.pdf_hash in error
    assert drafts(database) == []
    assert status(database)[0] == "held_pending_clearance"
    assert digest(database) == before


def test_invalid_packet_is_rejected(workspace):
    database = assessed(workspace)
    before = digest(database)
    bad = run()
    del bad["fields"]["composition"]
    assert workspace.stage_drafts(workspace.extraction_packet([bad])) == 1
    assert drafts(database) == []
    assert digest(database) == before


# Replay and conflicts ---------------------------------------------------------------

def test_identical_replay_stages_nothing(workspace, capsys):
    database = assessed(workspace)
    workspace.stage_drafts(workspace.extraction_packet(two_runs()))
    before = drafts(database)
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet(two_runs())) == 0
    assert drafts(database) == before
    assert "0 rows staged" in capsys.readouterr().out


def test_replay_with_reordered_keys_is_identical(workspace):
    database = assessed(workspace)
    packet = workspace.extraction_packet()
    workspace.stage_drafts(packet)
    reordered = {key: packet[key] for key in reversed(list(packet))}
    reordered["runs"] = [{key: value for key, value in reversed(list(packet["runs"][0].items()))}]
    assert workspace.stage_drafts(reordered) == 0
    assert len(drafts(database)) == 1


def test_changed_content_is_a_conflict(workspace, capsys):
    database = assessed(workspace)
    workspace.stage_drafts(workspace.extraction_packet())
    before = drafts(database)
    changed = run(composition=field(value={"formula": "EuSn2As2"}, raw_value="EuSn2As2"))
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet([changed])) == 1
    error = capsys.readouterr().err
    assert "conflict: draft_id 'draft-p1-r1'" in error
    assert "stored:" in error and "incoming:" in error and "EuSn2As2" in error
    assert drafts(database) == before


def test_conflict_rolls_back_the_whole_batch(workspace):
    database = assessed(workspace)
    workspace.stage_drafts(workspace.extraction_packet([run("draft-p1-r1")]))
    batch = [run("draft-p1-r9", row=9), run("draft-p1-r1", row=5)]
    assert workspace.stage_drafts(workspace.extraction_packet(batch)) == 1
    assert [row[0] for row in drafts(database)] == ["draft-p1-r1"]


def test_draft_id_reused_under_another_version_is_a_conflict(workspace, capsys):
    database = assessed(workspace)
    workspace.stage_drafts(workspace.extraction_packet())
    replacement, new_hash = workspace.make_pdf("log-1-901.pdf", b"%PDF-1.4\n% replacement\n")
    workspace.risk_assess(workspace.risk_packet(file_hash=new_hash), source_pdf=replacement)
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet(file_hash=new_hash)) == 1
    assert "another PDF version" in capsys.readouterr().err
    assert len(drafts(database)) == 1


# Technical failures (6.3, 14.7, 14.8) ------------------------------------------------

def explode(*args, **kwargs):
    raise RuntimeError("simulated database error")


def test_unexpected_error_records_technical_failure_and_no_drafts(workspace, monkeypatch, capsys):
    database = assessed(workspace)
    monkeypatch.setattr(draft_store, "mark_extraction_complete", explode)
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet(two_runs())) == 1
    assert "recorded as a technical failure" in capsys.readouterr().err
    assert drafts(database) == []
    state, reason = status(database)
    assert state == "technical_failure" and "simulated database error" in reason
    assert query(database, "SELECT count(*) FROM growth_runs")[0][0] == 0


def test_retry_after_technical_failure_recovers(workspace, monkeypatch):
    database = assessed(workspace)
    with monkeypatch.context() as patch:
        patch.setattr(draft_store, "mark_extraction_complete", explode)
        workspace.stage_drafts(workspace.extraction_packet())
    assert status(database)[0] == "technical_failure"
    assert workspace.stage_drafts(workspace.extraction_packet()) == 0
    assert status(database) == ("extraction_complete", None)
    assert len(drafts(database)) == 1


def test_risk_assess_error_on_registered_version_records_failure(workspace, monkeypatch):
    database = assessed(workspace)
    monkeypatch.setattr(status_store, "record_assessment", explode)
    assert workspace.risk_assess(workspace.risk_packet("critical", ISSUE)) == 1
    state, reason = status(database)
    assert state == "technical_failure" and "risk-assess failed" in reason


def test_rejections_never_record_a_failure(workspace):
    database = assessed(workspace, "critical", ISSUE)
    before = digest(database)
    workspace.stage_drafts(workspace.extraction_packet())          # gate rejection
    workspace.stage_drafts(workspace.extraction_packet(file_hash="e" * 64))  # unregistered version
    assert status(database)[0] == "held_pending_clearance"
    assert digest(database) == before


# Reserved guard (6.9, 30.2 to 30.4) -------------------------------------------------

def test_reserved_pdf_is_refused_without_flag(workspace, capsys):
    database = workspace.database("test")
    workspace.risk_assess(workspace.risk_packet(), database=database)
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    capsys.readouterr()
    assert workspace.stage_drafts(workspace.extraction_packet(), database=database) == 1
    assert "reserved for the acceptance run" in capsys.readouterr().err
    assert drafts(database) == []


def test_reserved_pdf_is_staged_with_flag(workspace):
    database = workspace.database("test")
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    workspace.risk_assess(workspace.risk_packet(), database=database, acceptance_run=True)
    assert workspace.stage_drafts(workspace.extraction_packet(), database=database, acceptance_run=True) == 0
    assert len(drafts(database)) == 1


def test_check_gate_is_never_guarded(workspace):
    database = workspace.database("test")
    workspace.risk_assess(workspace.risk_packet(), database=database)
    workspace.reserve(PLACEHOLDER_DRIVE_ID)
    assert staging.main(["check-gate", PLACEHOLDER_DRIVE_ID, workspace.pdf_hash, str(database)]) == 0
