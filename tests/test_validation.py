"""Tests for packet validation (Task 3.6, Requirements 21.1, 21.2, 21.4, 21.5, 21.6)."""

import hashlib
import json

import pytest

from factories import clone, extraction_packet, field, risk_packet, run
from staging_lib.packet import PacketError, load_packet, validate_packet
from staging_lib.source_pdf import sha256_file, verify_file_hash
from staging_lib.validate_envelope import validate_envelope
from staging_lib.validate_extraction import validate_extraction
from staging_lib.validate_risk import validate_risk


# Valid packets --------------------------------------------------------------

def test_valid_risk_packet_passes():
    assert validate_packet(risk_packet(), "risk") is None


def test_valid_risk_packet_with_issues_passes():
    packet = risk_packet("critical", issues=[
        {"reason": "ratio basis unclear", "source_location": {"pdf_index": 1, "row": 2}},
        {"reason": "page could not be read", "source_location": None},
    ])
    assert validate_packet(packet, "risk") is None


def test_valid_extraction_packet_passes():
    assert validate_packet(extraction_packet(), "extraction") is None


# Envelope (21.1, 21.2) -------------------------------------------------------

def test_missing_schema_version():
    packet = risk_packet()
    del packet["schema_version"]
    assert "schema_version" in validate_envelope(packet)


@pytest.mark.parametrize("version", [2, 0, "1", True, None, 1.0])
def test_unsupported_schema_version(version):
    assert "schema_version" in validate_envelope(risk_packet(schema_version=version))


@pytest.mark.parametrize("key", ["stage", "drive_file_id", "file_hash", "model", "prompt_version"])
@pytest.mark.parametrize("bad", ["missing", "", "   ", 7, None])
def test_required_envelope_strings(key, bad):
    packet = risk_packet()
    if bad == "missing":
        del packet[key]
    else:
        packet[key] = bad
    assert key in validate_envelope(packet)


def test_unknown_stage():
    packet = risk_packet()
    packet["stage"] = "review"
    assert "unknown stage" in validate_envelope(packet)


def test_packet_must_be_an_object():
    assert validate_envelope(["not", "an", "object"]) == "packet must be a JSON object"


def test_stage_must_match_command():
    assert "expected a extraction packet" in validate_packet(risk_packet(), "extraction")


# Risk fields (21.4) ----------------------------------------------------------

@pytest.mark.parametrize("decision", ["Critical", "non-critical", "", None, "ok"])
def test_invalid_decision(decision):
    assert "decision" in validate_risk(risk_packet(decision))


@pytest.mark.parametrize("issues", [None, {}, "none", 0])
def test_issues_must_be_an_array(issues):
    packet = risk_packet()
    packet["issues"] = issues
    assert "issues must be an array" in validate_risk(packet)


@pytest.mark.parametrize("issue, message", [
    ("text", "must be an object"),
    ({"source_location": None}, "reason"),
    ({"reason": " ", "source_location": None}, "reason"),
    ({"reason": "unclear"}, "source_location"),
    ({"reason": "unclear", "source_location": "page 1"}, "object or null"),
])
def test_invalid_issue(issue, message):
    assert message in validate_risk(risk_packet("critical", issues=[issue]))


# Extraction fields (21.5) ----------------------------------------------------

@pytest.mark.parametrize("runs, message", [
    (None, "runs must be an array"),
    ({}, "runs must be an array"),
    ([], "runs is empty"),
    (["run"], "must be an object"),
])
def test_invalid_runs(runs, message):
    packet = extraction_packet()
    packet["runs"] = runs
    assert message in validate_extraction(packet)


@pytest.mark.parametrize("draft_id", [None, "", "  ", 3])
def test_draft_id_required(draft_id):
    bad = run()
    bad["draft_id"] = draft_id
    assert "draft_id" in validate_extraction(extraction_packet([bad]))


def test_duplicate_draft_id_in_packet():
    packet = extraction_packet([run("d1"), run("d1", row=2)])
    assert "more than once" in validate_extraction(packet)


@pytest.mark.parametrize("locations", [
    None, [], "page 1", ["p1"],
    [{"pdf_index": 1}], [{"row": 1}],
    [{"pdf_index": 0, "row": 1}], [{"pdf_index": 1, "row": 0}],
    [{"pdf_index": "1", "row": 1}], [{"pdf_index": True, "row": 1}],
])
def test_invalid_source_locations(locations):
    bad = run()
    bad["source_locations"] = locations
    assert "source" in validate_extraction(extraction_packet([bad]))


def test_run_spanning_pages_is_valid():
    spanning = run()
    spanning["source_locations"] = [{"pdf_index": 1, "row": 4}, {"pdf_index": 2, "row": 1}]
    assert validate_extraction(extraction_packet([spanning])) is None


def test_missing_field_key():
    bad = run()
    del bad["fields"]["composition"]
    assert "missing composition" in validate_extraction(extraction_packet([bad]))


def test_pilot_field_keys_are_rejected():
    bad = run()
    bad["fields"]["technique"] = field()
    assert "unknown keys technique" in validate_extraction(extraction_packet([bad]))


@pytest.mark.parametrize("part", ["status", "raw_value", "value", "evidence"])
def test_field_part_required(part):
    bad = run()
    del bad["fields"]["growth_date"][part]
    assert f"missing {part}" in validate_extraction(extraction_packet([bad]))


@pytest.mark.parametrize("status", ["not_recorded", "illegible", "", None])
def test_invalid_field_status(status):
    bad = run(composition=field(status=status))
    assert "invalid status" in validate_extraction(extraction_packet([bad]))


@pytest.mark.parametrize("status", ["recorded", "inferred", "derived", "missing",
                                    "unreadable", "ambiguous", "omitted"])
def test_every_design_status_is_accepted(status):
    good = run(furnace_layout=field(value=None, status=status, raw_value=None,
                                    evidence="layout box on page 1"))
    assert validate_extraction(extraction_packet([good])) is None


@pytest.mark.parametrize("evidence", ["", "  ", None, 5])
def test_evidence_required(evidence):
    bad = run(timestamps=field(evidence=evidence))
    assert "evidence" in validate_extraction(extraction_packet([bad]))


def test_raw_value_must_be_text_or_null():
    bad = run(jc_number=field(raw_value=1302))
    assert "raw_value" in validate_extraction(extraction_packet([bad]))


# Source PDF hash (8.5) -------------------------------------------------------

def test_hash_matches(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder bytes")
    expected = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert sha256_file(pdf) == expected
    assert verify_file_hash(pdf, expected) is None
    assert verify_file_hash(pdf, expected.upper()) is None


def test_hash_mismatch(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder bytes")
    assert "do not match file_hash" in verify_file_hash(pdf, "0" * 64)


def test_missing_pdf(tmp_path):
    assert "not found" in verify_file_hash(tmp_path / "absent.pdf", "0" * 64)


# Loading (21.6) --------------------------------------------------------------

def write(tmp_path, content):
    path = tmp_path / "packet.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return path


def test_load_valid_packet(tmp_path):
    packet = load_packet(write(tmp_path, risk_packet()), "risk")
    assert packet["decision"] == "non_critical"


def test_load_malformed_json(tmp_path):
    with pytest.raises(PacketError, match="not valid JSON"):
        load_packet(write(tmp_path, "{not json"), "risk")


def test_load_missing_file(tmp_path):
    with pytest.raises(PacketError, match="not found"):
        load_packet(tmp_path / "absent.json", "risk")


def test_load_reports_validation_error(tmp_path):
    with pytest.raises(PacketError, match="decision"):
        load_packet(write(tmp_path, risk_packet("maybe")), "risk")


def test_validation_does_not_modify_the_packet():
    packet = extraction_packet()
    before = clone(packet)
    validate_packet(packet, "extraction")
    assert packet == before
