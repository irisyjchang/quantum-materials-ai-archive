"""Builders for synthetic test packets. All IDs are placeholders, never real lab data."""

import copy

from staging_lib.validate_extraction import FIELD_KEYS

PLACEHOLDER_DRIVE_ID = "placeholder-drive-id-1"
PLACEHOLDER_HASH = "0" * 64


def envelope(stage, **overrides):
    packet = {
        "schema_version": 1,
        "stage": stage,
        "drive_file_id": PLACEHOLDER_DRIVE_ID,
        "file_hash": PLACEHOLDER_HASH,
        "model": "placeholder-model",
        "prompt_version": "stage-log-runs-v1",
    }
    packet.update(overrides)
    return packet


def risk_packet(decision="non_critical", issues=None, **overrides):
    packet = envelope("risk", **overrides)
    packet["decision"] = decision
    packet["issues"] = [] if issues is None else issues
    return packet


def field(value="value", status="recorded", raw_value="as written", evidence="page 1, row 1"):
    return {"status": status, "raw_value": raw_value, "value": value, "evidence": evidence}


def run(draft_id="draft-p1-r1", pdf_index=1, row=1, **field_overrides):
    fields = {key: field() for key in FIELD_KEYS}
    fields["jc_number"] = field(value="JC1302", raw_value="JC1302")
    fields["growth_date"] = field(value="2020-01-16", raw_value="1/16/2020")
    fields.update(field_overrides)
    return {
        "draft_id": draft_id,
        "source_locations": [{"pdf_index": pdf_index, "row": row}],
        "fields": fields,
    }


def extraction_packet(runs=None, **overrides):
    packet = envelope("extraction", **overrides)
    packet["runs"] = [run()] if runs is None else runs
    return packet


def clone(packet):
    return copy.deepcopy(packet)
