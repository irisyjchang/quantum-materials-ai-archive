"""Lint test for the stage-log-runs skill instructions (Tasks 8.3, 8.4).

Requirements 1.1, 1.10, 1.11, 2.1, 2.5, 3.1, 30.7. These checks keep SKILL.md in
step with the staging tool; they do not test how Codex behaves.
"""

import re
import shlex
from pathlib import Path

import pytest

import staging

SKILL = (Path(__file__).resolve().parents[1] / ".agents" / "skills" / "stage-log-runs" / "SKILL.md").read_text(
    encoding="utf-8")
TEXT = " ".join(SKILL.split())  # collapse line breaks for phrase checks

COMMANDS = {
    "lookup": "python tools/lookup_drive_id.py <archive_filename>",
    "risk-assess": "python staging.py risk-assess <packet.json> --source-pdf <local path> [--acceptance-run] <database.sqlite>",
    "check-gate": "python staging.py check-gate <drive_file_id> <file_hash> <database.sqlite>",
    "stage-drafts": "python staging.py stage-drafts <packet.json> [--acceptance-run] <database.sqlite>",
}


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_command_lines_are_present(name):
    assert COMMANDS[name] in SKILL


@pytest.mark.parametrize("name", ["risk-assess", "check-gate", "stage-drafts"])
@pytest.mark.parametrize("acceptance_run", [False, True])
def test_command_lines_parse_with_the_real_staging_tool(name, acceptance_run):
    """Every staging command in SKILL.md is accepted by staging.py's own argument parser."""
    line = COMMANDS[name]
    if acceptance_run and "[--acceptance-run]" not in line:
        pytest.skip("command has no acceptance-run flag")
    line = line.replace(" [--acceptance-run]", " --acceptance-run" if acceptance_run else "")
    line = re.sub(r"<[^>]+>", "placeholder", line)
    argv = shlex.split(line)[2:]  # drop "python staging.py"
    args = staging.build_parser().parse_args(argv)
    assert args.command == name


def test_lookup_runs_before_assessment_and_stops_when_unlisted():
    assert TEXT.index(COMMANDS["lookup"]) < TEXT.index(COMMANDS["risk-assess"])
    assert "If lookup exits nonzero, stop for that PDF" in TEXT


def test_model_and_prompt_version_are_never_blank():
    assert "Never leave `model` or `prompt_version` blank" in TEXT
    assert "`prompt_version` to `stage-log-runs-v2`" in TEXT


def test_commands_appear_in_order():
    positions = [TEXT.index(COMMANDS[name]) for name in ("risk-assess", "check-gate", "stage-drafts")]
    assert positions == sorted(positions)


def test_lower_table_rule():
    assert "Issues confined to the lower table do not raise the risk tier" in TEXT


def test_whole_pdf_is_held():
    assert "hold the whole PDF" in TEXT


def test_extracts_from_the_path_printed_by_check_gate():
    assert "use the retained PDF path printed after `cleared`" in TEXT
    assert "Read the retained PDF returned by `check-gate`" in TEXT


def test_zero_extraction_packets_when_not_cleared():
    assert "produce zero extraction packets" in TEXT


def test_never_claims_success_without_a_command_result():
    assert "never claim the assessment was recorded" in TEXT
    assert "Never claim drafts were staged without a successful command result" in TEXT


def test_acceptance_run_flag_only_when_stated():
    assert "Add `--acceptance-run`" in TEXT
    assert "only when the operator explicitly identifies a formal acceptance run in Test" in TEXT


def test_resume_after_clearance_uses_same_version():
    assert "After clearance, resume with the same ID and hash" in TEXT
