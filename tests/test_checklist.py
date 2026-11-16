"""Tests for the Test checklist validator (Tasks 24.3 and 24.7).

Requirements 27.1, 27.2, 27.7 to 27.10, 27.12 to 27.14, 28.1 to 28.3, 28.8, 28.12, 28.14 to 28.18,
30.1, 30.8, 30.9. Synthetic checklists with placeholder IDs only; no lab PDFs are identified.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from common.config import load_config
from review_app.app import create_app
from staging_lib.validate_extraction import FIELD_KEYS
from tools import check_checklist
from tools.check_checklist import CRITICAL_CASES, MISSING_INFORMATION_CASES, STRUCTURAL_CASES, check

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "test_checklist.template.json"


def placeholder_hash(number):
    return f"{number:064x}"


def evidence(case, *locations, observation="placeholder observation", observed_by="Placeholder Reviewer"):
    locations = locations or ({"pdf_index": 1, "row": 1},)
    return {"case": case, "source_locations": list(locations), "observation": observation,
            "observed_by": observed_by}


def pdf(number, binder=1, **fields):
    """A walkthrough PDF entry with evidence for every case it claims."""
    entry = {"filename": f"log-{binder}-{number:03d}.pdf", "drive_file_id": f"placeholder-drive-{number}",
             "file_hash": placeholder_hash(number), **fields}
    claimed = list(entry.get("missing_information_cases", [])) + list(entry.get("structural_cases", []))
    if isinstance(entry.get("critical_case"), str):
        claimed.append(entry["critical_case"])
    if entry.get("has_furnace_layout_sketch"):
        claimed.append("furnace_layout_sketch")
    entry["case_evidence"] = [
        evidence(case, {"pdf_index": 1, "row": 2}, {"pdf_index": 2, "row": 1}) if case == "run_spans_pages"
        else evidence(case) for case in claimed]
    return entry


def flag_one_critical_run(entry):
    entry["one_critical_run"] = True
    entry["case_evidence"].append(evidence("one_critical_run", {"pdf_index": 1, "row": 3}))


def expected_run(row, status="approve", page=1):
    run = {"source_locations": [{"pdf_index": page, "row": row}], "researcher_name": "Placeholder",
           "growth_date": "2018-10", "jc_number": None, "stoichiometry": "MoSe2",
           "blank_or_flagged_fields": [{"field": "jc_number", "expectation": "blank",
                                        "reason": "JC cell is empty on the scan"}],
           "expected_status": status}
    if status == "approve":
        run["search_terms"] = {"month": "2018-10", "name": "Placeholder"}
    else:
        run["hold_reason"] = "ratio unclear"
    return run


def acceptance(number, **fields):
    entry = {"filename": f"log-2-{number:03d}.pdf", "drive_file_id": f"placeholder-drive-{number}",
             "file_hash": placeholder_hash(number), "reservation_status": "confirmed",
             "expected_risk_tier": "non_critical", "expected_hold_stage": None, "expected_hold_reason": None,
             "expected_run_count": 2, "expected_runs": [expected_run(1), expected_run(2)],
             "expected_recorded_by": "Placeholder Reviewer", "expected_recorded_at": "2026-11-01T09:00:00+00:00",
             "first_run_at": None, "unnecessary_holds": None, "extraction_errors_found_in_review": None,
             "reviewer_correction_time": None}
    entry.update(fields)
    return entry


def provisional(number, **fields):
    return {"filename": f"log-2-{number:03d}.pdf", "drive_file_id": f"placeholder-drive-{number}",
            "reservation_status": "provisional", **fields}


def complete():
    """A synthetic checklist that passes every check."""
    walkthrough = [
        pdf(1, binder=1, missing_information_cases=list(MISSING_INFORMATION_CASES[:5]),
            structural_cases=["clear_single_run", "run_spans_pages"], has_furnace_layout_sketch=True),
        pdf(2, binder=2, missing_information_cases=list(MISSING_INFORMATION_CASES[5:]),
            structural_cases=["multi_run_all_eligible", "carried_down_compound", "entries_in_both_tables"]),
    ]
    for offset, case in enumerate(CRITICAL_CASES, 10):
        tier = "uncertain" if case == "cannot_be_reliably_assessed" else "critical"
        walkthrough.append(pdf(offset, binder=1 + offset % 2, critical_case=case, expected_tier=tier))
    flag_one_critical_run(walkthrough[2])
    return {
        "tool_versions": {"skill": "stage-log-runs@abc123", "staging_tool": "abc123", "review_app": "abc123"},
        "feedback": {},
        "walkthrough": walkthrough,
        "acceptance": [
            acceptance(101),
            acceptance(102, expected_risk_tier="critical", expected_hold_stage="before_extraction",
                       expected_hold_reason="ambiguous ratio", expected_run_count=3, expected_runs=[]),
            acceptance(103, expected_hold_stage="in_review", expected_hold_reason="unit unclear in review",
                       expected_run_count=1, expected_runs=[expected_run(1, status="hold")]),
        ],
    }


def failures(data, **options):
    return check(data, **options).failures


def critical_entry(data, case):
    return next(entry for entry in data["walkthrough"] if entry.get("critical_case") == case)


def test_complete_synthetic_checklist_passes():
    report = check(complete())
    assert report.ok, report.failures
    assert report.warnings == []


# Template and local checklist (30.1, 30.8, 30.9) ---------------------------------------------------

def test_template_names_no_drive_ids_hashes_or_observations():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert data["walkthrough"] == [] and data["acceptance"] == []
    text = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"[0-9a-f]{64}", text)
    for shape in data["entry_templates"].values():
        if isinstance(shape, dict) and "drive_file_id" in shape:
            assert shape["drive_file_id"] == ""
    candidates = data["design_mvp_candidates_not_reserved"]["candidates"]
    assert [item["filename"] for item in candidates] == [
        "log-1-008.pdf", "log-2-045.pdf", "log-1-077.pdf", "log-2-146.pdf", "log-2-097.pdf", "log-2-199.pdf"]
    assert all(set(item) == {"filename", "candidate_note"} for item in candidates)
    assert "Hold candidate only" in candidates[-1]["candidate_note"]


def test_template_fails_with_missing_items(capsys):
    assert check_checklist.main([str(TEMPLATE)]) == 1
    output = capsys.readouterr().out
    assert "is not ready" in output
    for expected in ("no PDF from Binder 1", "missing_researcher_name", "(a) no_usable_lookup_value",
                     "one_critical_run", "clear_single_run", "has_furnace_layout_sketch",
                     "tool_versions.skill", "before_extraction"):
        assert expected in output


def test_template_candidates_are_not_reserved_by_the_guard():
    from staging_lib.reserved_guard import load_reserved_ids

    assert load_reserved_ids(TEMPLATE) is None


def test_template_allowed_values_match_the_validator():
    allowed = json.loads(TEMPLATE.read_text(encoding="utf-8"))["entry_templates"]["allowed_values"]
    assert tuple(allowed["missing_information_cases"]) == MISSING_INFORMATION_CASES
    assert tuple(allowed["structural_cases"]) == STRUCTURAL_CASES
    assert {name: letter for letter, name in allowed["critical_case"].items()} == CRITICAL_CASES
    assert tuple(allowed["blank_or_flagged_field"]) == FIELD_KEYS


def test_repository_config_points_at_the_git_ignored_local_checklist():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert config["checklist_path"] == "test_checklist.local.json"
    assert "test_checklist.local.json" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_missing_local_checklist_fails_with_the_copy_command(workspace, capsys):
    assert not workspace.checklist_path.exists()
    assert check_checklist.main([]) == 1
    message = capsys.readouterr().err
    assert str(workspace.checklist_path) in message
    assert "cp test_checklist.template.json" in message


def test_guard_status_view_and_validator_read_the_same_checklist(workspace, capsys):
    """Requirement 30.9: one file at checklist_path serves all three readers."""
    assert load_config().checklist_path == workspace.checklist_path
    data = complete()
    data["acceptance"].append(provisional(150, candidate_outcome="possible hold before extraction"))
    reserved_id = data["acceptance"][-1]["drive_file_id"]
    workspace.checklist_path.write_text(json.dumps(data), encoding="utf-8")

    # The validator default reads it and reports the provisional entry.
    assert check_checklist.main([]) == 1
    output = capsys.readouterr().out
    assert str(workspace.checklist_path) in output and f"Drive ID {reserved_id}) is still provisional" in output
    assert check_checklist.main(["--walkthrough-only"]) == 0

    # The guard reserves the provisional entry.
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(drive_file_id=reserved_id), database=database) == 1
    assert "reserved for the acceptance run" in capsys.readouterr().err

    # The status view labels it once it is processed for the acceptance run.
    assert workspace.risk_assess(workspace.risk_packet(drive_file_id=reserved_id), database=database,
                                 acceptance_run=True) == 0
    page = create_app("test", root=workspace.root).test_client().get("/status").get_data(as_text=True)
    assert "Reserved (acceptance)" in page


def test_complete_checklist_passes_on_the_command_line(tmp_path, capsys):
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps(complete()), encoding="utf-8")
    assert check_checklist.main([str(path)]) == 0
    assert "passes" in capsys.readouterr().out


def test_unreadable_checklist_fails(tmp_path):
    path = tmp_path / "checklist.json"
    path.write_text("{broken", encoding="utf-8")
    assert check_checklist.main([str(path)]) == 1
    assert check_checklist.main([str(tmp_path / "absent.json")]) == 1


# Identity and overlap (27.1, 27.13, 28.1, 28.3) ----------------------------------------------------

@pytest.mark.parametrize("section,index", [("walkthrough", 0), ("acceptance", 0)])
@pytest.mark.parametrize("key", ["filename", "drive_file_id", "file_hash"])
def test_entry_without_identity_key_fails(section, index, key):
    data = complete()
    del data[section][index][key]
    assert any(f"missing {key}" in failure for failure in failures(data))


def test_malformed_file_hash_fails():
    data = complete()
    data["acceptance"][0]["file_hash"] = "ABC"
    assert any("64-character" in failure for failure in failures(data))


def test_walkthrough_entry_sharing_an_acceptance_drive_id_fails():
    data = complete()
    data["walkthrough"][0]["drive_file_id"] = data["acceptance"][0]["drive_file_id"]
    for options in ({}, {"walkthrough_only": True}):
        assert any("drive_file_id placeholder-drive-101 matches an acceptance entry" in f
                   for f in failures(data, **options))


@pytest.mark.parametrize("key", ["filename", "drive_file_id"])
def test_walkthrough_entry_matching_a_provisional_entry_fails(key):
    data = complete()
    data["acceptance"].append(provisional(150))
    data["walkthrough"][1][key] = data["acceptance"][-1][key]
    result = failures(data, walkthrough_only=True)
    assert len(result) == 1 and f"{key} " in result[0] and "matches an acceptance entry" in result[0]


@pytest.mark.parametrize("binder", [1, 2])
def test_walkthrough_without_a_binder_fails(binder):
    data = complete()
    other = 2 if binder == 1 else 1
    for entry in data["walkthrough"]:
        entry["filename"] = entry["filename"].replace(f"log-{binder}-", f"log-{other}-")
    assert f"walkthrough: no PDF from Binder {binder} (Requirement 27.1)" in failures(data)


def test_binder_field_is_used_when_the_filename_has_no_binder():
    data = complete()
    data["walkthrough"][1]["filename"] = "scan.pdf"
    assert any("binder unknown" in failure for failure in failures(data))
    data["walkthrough"][1]["binder"] = 2
    assert failures(data) == []


# Coverage (27.2, 27.7, 27.8, 27.9, 27.10) ----------------------------------------------------------

def drop_case(entry, key, case):
    entry[key].remove(case)
    entry["case_evidence"] = [item for item in entry["case_evidence"] if item["case"] != case]


@pytest.mark.parametrize("case", MISSING_INFORMATION_CASES)
def test_each_missing_information_case_is_required(case):
    data = complete()
    for entry in data["walkthrough"]:
        if case in entry.get("missing_information_cases", []):
            drop_case(entry, "missing_information_cases", case)
    assert failures(data) == [f"walkthrough: missing-information case {case} is not covered (Requirement 27.2)"]


def test_missing_information_case_on_a_critical_pdf_does_not_count():
    data = complete()
    drop_case(data["walkthrough"][0], "missing_information_cases", "missing_researcher_name")
    target = critical_entry(data, "missing_stoichiometry")
    target["missing_information_cases"] = ["missing_researcher_name"]
    target["case_evidence"].append(evidence("missing_researcher_name"))
    report = check(data)
    assert any("missing_researcher_name is not covered" in failure for failure in report.failures)
    assert any("are not counted" in warning for warning in report.warnings)


@pytest.mark.parametrize("case", list(CRITICAL_CASES))
def test_each_critical_case_is_required(case):
    data = complete()
    data["walkthrough"].remove(critical_entry(data, case))
    if not any(entry.get("one_critical_run") for entry in data["walkthrough"]):
        flag_one_critical_run(data["walkthrough"][3])
    message = (f"walkthrough: critical case ({CRITICAL_CASES[case]}) {case} has no dedicated PDF or waiver "
               "(Requirement 27.8)")
    assert failures(data) == [message]


def test_entry_naming_two_critical_cases_counts_for_neither():
    data = complete()
    first = critical_entry(data, "ambiguous_compound")
    data["walkthrough"].remove(critical_entry(data, "ambiguous_ratio"))
    first["critical_case"] = ["ambiguous_compound", "ambiguous_ratio"]
    first["case_evidence"].append(evidence("ambiguous_ratio"))
    result = failures(data)
    assert any("names more than one critical case" in failure for failure in result)
    assert any("(c) ambiguous_compound has no dedicated PDF" in failure for failure in result)
    assert any("(d) ambiguous_ratio has no dedicated PDF" in failure for failure in result)


def test_single_item_list_counts_as_one_critical_case():
    data = complete()
    critical_entry(data, "ambiguous_ratio")["critical_case"] = ["ambiguous_ratio"]
    assert failures(data) == []


def test_critical_entry_needs_a_critical_or_uncertain_tier():
    data = complete()
    critical_entry(data, "missing_stoichiometry")["expected_tier"] = "non_critical"
    result = failures(data)
    assert any("expected_tier for missing_stoichiometry must be critical or uncertain" in f for f in result)
    assert any("(b) missing_stoichiometry has no dedicated PDF" in f for f in result)


def test_case_j_must_be_expected_uncertain():
    data = complete()
    critical_entry(data, "cannot_be_reliably_assessed")["expected_tier"] = "critical"
    assert any("must be uncertain" in failure for failure in failures(data))


def test_unknown_case_names_fail():
    data = complete()
    data["walkthrough"][0]["structural_cases"].append("spiral_binding")
    data["walkthrough"][1]["missing_information_cases"].append("missing_coffee")
    critical_entry(data, "ambiguous_ratio")["critical_case"] = "ambigous_ratio"
    result = failures(data)
    assert any("unknown structural_cases value 'spiral_binding'" in f for f in result)
    assert any("unknown missing_information_cases value 'missing_coffee'" in f for f in result)
    assert any("unknown critical_case 'ambigous_ratio'" in f for f in result)


def test_waiver_with_a_reason_passes():
    data = complete()
    data["walkthrough"].remove(critical_entry(data, "unknown_ratio_basis"))
    data["walkthrough"].append({"critical_case": "unknown_ratio_basis", "no_example_found": True,
                                "waiver_reason": "No scan in either binder states a ratio basis."})
    assert failures(data) == []


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_waiver_without_a_reason_fails(reason):
    data = complete()
    data["walkthrough"].remove(critical_entry(data, "unknown_ratio_basis"))
    data["walkthrough"].append({"critical_case": "unknown_ratio_basis", "no_example_found": True,
                                "waiver_reason": reason})
    result = failures(data)
    assert any("needs a waiver_reason" in failure for failure in result)
    assert any("(h) unknown_ratio_basis has no dedicated PDF or waiver" in failure for failure in result)


def test_no_one_critical_run_entry_fails():
    data = complete()
    for entry in data["walkthrough"]:
        if entry.pop("one_critical_run", None):
            entry["case_evidence"] = [item for item in entry["case_evidence"] if item["case"] != "one_critical_run"]
    assert failures(data) == ["walkthrough: no multi-run PDF flagged one_critical_run: true (Requirement 27.9)"]


def test_one_critical_run_flag_without_a_critical_case_fails():
    data = complete()
    flag_one_critical_run(data["walkthrough"][0])
    assert any("one_critical_run needs the PDF's critical_case" in failure for failure in failures(data))


@pytest.mark.parametrize("case", STRUCTURAL_CASES)
def test_each_structural_case_is_required(case):
    data = complete()
    for entry in data["walkthrough"]:
        if case in entry.get("structural_cases", []):
            drop_case(entry, "structural_cases", case)
    assert failures(data) == [f"walkthrough: structural case {case} is not covered (Requirement 27.10)"]


def test_no_layout_sketch_pdf_fails():
    data = complete()
    entry = data["walkthrough"][0]
    entry["has_furnace_layout_sketch"] = False
    entry["case_evidence"] = [item for item in entry["case_evidence"] if item["case"] != "furnace_layout_sketch"]
    assert failures(data) == ["walkthrough: no PDF flagged has_furnace_layout_sketch: true (Requirement 27.7)"]


def test_layout_sketch_on_a_critical_pdf_does_not_count():
    data = complete()
    data["walkthrough"][0]["has_furnace_layout_sketch"] = False
    data["walkthrough"][0]["case_evidence"].pop()
    target = critical_entry(data, "ambiguous_ratio")
    target["has_furnace_layout_sketch"] = True
    target["case_evidence"].append(evidence("furnace_layout_sketch", {"pdf_index": 1, "row": None,
                                                                     "area": "Furnace Layout box"}))
    assert "walkthrough: no PDF flagged has_furnace_layout_sketch: true (Requirement 27.7)" in failures(data)


# Case evidence (27.12, 27.14) ----------------------------------------------------------------------

@pytest.mark.parametrize("case", ["missing_jc_number", "run_spans_pages", "furnace_layout_sketch"])
def test_claimed_case_without_evidence_fails(case):
    data = complete()
    entry = data["walkthrough"][0]
    entry["case_evidence"] = [item for item in entry["case_evidence"] if item["case"] != case]
    assert failures(data) == [f"walkthrough[0] log-1-001.pdf: no case_evidence for {case}; cite the page and row "
                              "(or area) and the observation that qualifies this PDF (Requirement 27.12)"]


@pytest.mark.parametrize("case", ["missing_stoichiometry", "one_critical_run"])
def test_critical_and_one_critical_run_claims_need_evidence(case):
    data = complete()
    entry = data["walkthrough"][2]
    assert entry["critical_case"] == "no_usable_lookup_value"
    if case == "missing_stoichiometry":
        entry = critical_entry(data, case)
    entry["case_evidence"] = [item for item in entry["case_evidence"] if item["case"] != case]
    assert any(f"no case_evidence for {case}" in failure for failure in failures(data))


def test_evidence_for_an_unclaimed_case_fails():
    data = complete()
    data["walkthrough"][1]["case_evidence"].append(evidence("clear_single_run"))
    assert any("case 'clear_single_run' is not one this entry claims" in f for f in failures(data))


@pytest.mark.parametrize("location,problem", [
    ({"pdf_index": 0, "row": 1}, "pdf_index must be a whole number of at least 1"),
    ({"pdf_index": 1, "row": 0}, "row must be a whole number of at least 1"),
    ({"pdf_index": 1, "row": None}, "row is null, so name the area"),
    ({"pdf_index": 1, "row": None, "area": "  "}, "row is null, so name the area"),
    ("page 1", "must be a JSON object"),
])
def test_bad_evidence_location_fails(location, problem):
    data = complete()
    data["walkthrough"][1]["case_evidence"][0]["source_locations"] = [location]
    assert any(problem in failure for failure in failures(data))


def test_area_without_row_is_accepted_for_evidence():
    data = complete()
    data["walkthrough"][1]["case_evidence"][0]["source_locations"] = [
        {"pdf_index": 1, "row": None, "area": "shared header"}]
    assert failures(data) == []


@pytest.mark.parametrize("key", ["observation", "observed_by"])
def test_evidence_needs_observation_and_observer(key):
    data = complete()
    data["walkthrough"][1]["case_evidence"][0][key] = ""
    assert any(f"{key} is not recorded" in failure for failure in failures(data))


def test_evidence_needs_at_least_one_location():
    data = complete()
    data["walkthrough"][1]["case_evidence"][0]["source_locations"] = []
    assert any("source_locations must list at least one page" in failure for failure in failures(data))


def test_spanning_pages_evidence_on_one_page_fails():
    data = complete()
    item = next(i for i in data["walkthrough"][0]["case_evidence"] if i["case"] == "run_spans_pages")
    item["source_locations"] = [{"pdf_index": 1, "row": 5}, {"pdf_index": 1, "row": 6}]
    assert any("run_spans_pages evidence must cite at least two pages" in f for f in failures(data))


def test_waivers_need_no_evidence():
    data = complete()
    data["walkthrough"].remove(critical_entry(data, "unknown_ratio_basis"))
    data["walkthrough"].append({"critical_case": "unknown_ratio_basis", "no_example_found": True,
                                "waiver_reason": "No example in either binder."})
    assert failures(data, walkthrough_only=True) == []


# Reservation status (28.15 to 28.17) ---------------------------------------------------------------

def test_provisional_entries_block_acceptance_readiness_and_are_reported():
    data = complete()
    data["acceptance"].append(provisional(150, candidate_outcome="may need a hold before extraction"))
    result = failures(data)
    assert result == ["acceptance[3] log-2-150.pdf (Drive ID placeholder-drive-150) is still provisional: a "
                      "reviewer must check the scan, record file_hash and the expected outcomes, then set "
                      "reservation_status to confirmed (Requirements 28.15 to 28.17)"]


def test_provisional_entries_pass_walkthrough_only_without_hash_or_outcomes():
    data = complete()
    data["acceptance"] = [provisional(150 + n) for n in range(6)]
    del data["tool_versions"]
    assert failures(data, walkthrough_only=True) == []


@pytest.mark.parametrize("key", ["filename", "drive_file_id"])
def test_provisional_entry_needs_filename_and_drive_id(key):
    data = complete()
    data["acceptance"].append(provisional(150))
    del data["acceptance"][-1][key]
    assert any(f"missing {key}" in failure for failure in failures(data, walkthrough_only=True))


def test_reservation_status_is_required():
    data = complete()
    del data["acceptance"][0]["reservation_status"]
    for options in ({}, {"walkthrough_only": True}):
        assert any("reservation_status must be provisional or confirmed" in f for f in failures(data, **options))


def test_candidate_outcome_does_not_count_as_an_expected_hold():
    data = complete()
    data["acceptance"][1] = provisional(102, candidate_outcome="hold before extraction if rows cannot be tied")
    result = failures(data)
    assert any("is still provisional" in f for f in result)
    assert "acceptance: no confirmed entry has expected_hold_stage before_extraction (Requirement 28.8)" in result


# Acceptance outcomes (28.2, 28.8, 28.12, 28.18) ----------------------------------------------------

def test_missing_tool_versions_fails():
    data = complete()
    del data["tool_versions"]
    assert any(failure.startswith("tool_versions is missing") for failure in failures(data))


@pytest.mark.parametrize("key", ["skill", "staging_tool", "review_app"])
def test_incomplete_tool_versions_fail(key):
    data = complete()
    data["tool_versions"][key] = None
    assert failures(data) == [f"tool_versions.{key} is not recorded (Requirement 28.12)"]


def test_walkthrough_only_skips_acceptance_outcome_checks():
    data = complete()
    del data["tool_versions"]
    data["acceptance"] = [{"filename": "log-2-999.pdf", "drive_file_id": "placeholder-drive-999",
                           "reservation_status": "confirmed"}]
    assert failures(data, walkthrough_only=True) == []


def test_no_before_extraction_entry_fails():
    data = complete()
    del data["acceptance"][1]
    assert failures(data) == ["acceptance: no confirmed entry has expected_hold_stage before_extraction "
                              "(Requirement 28.8)"]


@pytest.mark.parametrize("key,value", [
    ("expected_risk_tier", None), ("expected_run_count", None), ("expected_runs", None),
])
def test_acceptance_entry_without_expected_outcome_fails(key, value):
    data = complete()
    data["acceptance"][0][key] = value
    assert any("no expected outcome" in failure for failure in failures(data))


def test_run_spanning_pages_lists_every_page_and_row():
    data = complete()
    data["acceptance"][0]["expected_runs"][0]["source_locations"] = [
        {"pdf_index": 1, "row": 7}, {"pdf_index": 2, "row": 1}, {"pdf_index": 2, "row": 2}]
    assert failures(data) == []


@pytest.mark.parametrize("locations,problem", [
    (None, "source_locations must list every page and row"),
    ([], "source_locations must list every page and row"),
    ([{"pdf_index": 1, "row": None, "area": "shared header"}], "row must be a whole number of at least 1"),
    ([{"pdf_index": 0, "row": 1}], "pdf_index must be a whole number of at least 1"),
    ([{"pdf_index": 1, "row": 2}, {"pdf_index": 1, "row": 2}], "page 1, row 2 is listed twice"),
])
def test_bad_expected_source_locations_fail(locations, problem):
    data = complete()
    data["acceptance"][0]["expected_runs"][0]["source_locations"] = locations
    assert any(problem in failure for failure in failures(data))


def test_old_source_page_and_row_keys_are_rejected():
    data = complete()
    run = data["acceptance"][0]["expected_runs"][0]
    run["source_page"], run["source_row"] = 1, 1
    result = failures(data)
    assert sum("is replaced by source_locations" in failure for failure in result) == 2


def test_blank_or_flagged_fields_must_be_recorded():
    data = complete()
    del data["acceptance"][0]["expected_runs"][0]["blank_or_flagged_fields"]
    assert any("record blank_or_flagged_fields" in failure for failure in failures(data))


def test_empty_blank_or_flagged_list_is_an_explicit_none():
    data = complete()
    run = data["acceptance"][0]["expected_runs"][0]
    run["jc_number"], run["blank_or_flagged_fields"] = "697", []
    assert failures(data) == []


@pytest.mark.parametrize("item,problem", [
    ({"field": "colour", "expectation": "blank", "reason": "x"}, "field must be one of"),
    ({"field": "timestamps", "expectation": "maybe", "reason": "x"}, "expectation must be blank or flagged"),
    ({"field": "timestamps", "expectation": "blank", "reason": ""}, "give the reason timestamps should be blank"),
    ({"field": "timestamps", "expectation": "blank", "reason": "x", "expected_field_status": "ambiguous"},
     "expected_field_status for a blank field must be missing or omitted"),
    ({"field": "growth_process", "expectation": "flagged", "reason": "x", "expected_field_status": "missing"},
     "expected_field_status for a flagged field must be inferred or derived or unreadable or ambiguous"),
    ({"field": "furnace_layout", "expectation": "flagged", "reason": "x",
      "source_location": {"pdf_index": 1, "row": None}}, "row is null, so name the area"),
])
def test_bad_blank_or_flagged_items_fail(item, problem):
    data = complete()
    data["acceptance"][0]["expected_runs"][0]["blank_or_flagged_fields"].append(item)
    assert any(problem in failure for failure in failures(data))


def test_flagged_fields_with_status_and_location_pass():
    data = complete()
    data["acceptance"][0]["expected_runs"][0]["blank_or_flagged_fields"] += [
        {"field": "growth_process", "expectation": "flagged", "reason": "only implied by the firing pattern",
         "expected_field_status": "inferred", "source_location": {"pdf_index": 1, "row": None,
                                                                  "area": "Firing Pattern box"}},
        {"field": "timestamps", "expectation": "blank", "reason": "timestamp cells are empty",
         "expected_field_status": "missing"},
    ]
    assert failures(data) == []


def test_field_listed_twice_fails():
    data = complete()
    run = data["acceptance"][0]["expected_runs"][0]
    run["blank_or_flagged_fields"].append({"field": "jc_number", "expectation": "flagged", "reason": "x"})
    assert any("field jc_number is listed more than once" in f for f in failures(data))


@pytest.mark.parametrize("field_name,value_key", [
    ("researcher_name", "researcher_name"), ("growth_date", "growth_date"), ("jc_number", "jc_number"),
    ("composition", "stoichiometry"),
])
def test_blank_field_needs_a_null_expected_value(field_name, value_key):
    data = complete()
    run = data["acceptance"][2]["expected_runs"][0]
    run[value_key] = "something"
    run["blank_or_flagged_fields"] = [{"field": field_name, "expectation": "blank", "reason": "cell is empty"}]
    assert any(f"{field_name} is expected blank, so {value_key} must be null" in f for f in failures(data))


def test_expected_approved_run_cannot_expect_composition_blank():
    data = complete()
    run = data["acceptance"][0]["expected_runs"][0]
    run["stoichiometry"] = None
    run["blank_or_flagged_fields"].append({"field": "composition", "expectation": "blank", "reason": "no compound"})
    assert any("cannot expect composition blank" in f for f in failures(data))


def test_expected_approved_run_needs_a_lookup_value():
    data = complete()
    run = data["acceptance"][0]["expected_runs"][0]
    run["researcher_name"] = run["growth_date"] = run["jc_number"] = None
    assert any("needs a researcher_name, growth_date, or jc_number" in f for f in failures(data))


def test_expected_runs_must_match_the_run_count():
    data = complete()
    data["acceptance"][0]["expected_run_count"] = 3
    assert any("lists 2 runs but expected_run_count is 3" in f for f in failures(data))


def test_expected_approved_run_needs_search_terms_and_held_run_a_reason():
    data = complete()
    del data["acceptance"][0]["expected_runs"][0]["search_terms"]
    data["acceptance"][2]["expected_runs"][0]["hold_reason"] = ""
    result = failures(data)
    assert any("needs search_terms" in f for f in result)
    assert any("an expected-held run needs a hold_reason" in f for f in result)


def test_before_extraction_hold_needs_a_reason_and_a_critical_tier():
    data = complete()
    data["acceptance"][1]["expected_hold_reason"] = None
    data["acceptance"][1]["expected_risk_tier"] = "non_critical"
    result = failures(data)
    assert any("needs an expected_hold_reason" in f for f in result)
    assert any("cannot be expected to stay held before extraction" in f for f in result)


@pytest.mark.parametrize("key", ["expected_recorded_by", "expected_recorded_at"])
def test_acceptance_entry_without_reviewer_or_time_fails(key):
    data = complete()
    data["acceptance"][0][key] = None
    assert any(key in failure and "log-2-101.pdf" in failure for failure in failures(data))


def test_expected_recorded_at_without_time_zone_fails():
    data = complete()
    data["acceptance"][0]["expected_recorded_at"] = "2026-11-01T09:00:00"
    assert any("with a time zone" in failure for failure in failures(data))


def test_expected_outcomes_must_be_recorded_before_the_first_run():
    data = complete()
    data["acceptance"][0]["first_run_at"] = "2026-10-31T09:00:00+00:00"
    assert any("log-2-101.pdf: expected_recorded_at is later than first_run_at" in f for f in failures(data))
    data["acceptance"][0]["first_run_at"] = "2026-11-01T09:00:00+00:00"
    assert failures(data) == []
    data["acceptance"][0]["first_run_at"] = "2026-11-02T09:00:00+00:00"
    assert failures(data) == []


def test_no_draft_expected_held_in_review_is_a_warning_only():
    data = complete()
    data["acceptance"][2]["expected_hold_stage"] = None
    data["acceptance"][2]["expected_runs"] = [expected_run(1)]
    report = check(data)
    assert report.ok and any("held in review" in warning for warning in report.warnings)


# Results (28.14) -----------------------------------------------------------------------------------

def with_results(data, value=0):
    data = copy.deepcopy(data)
    for entry in data["acceptance"]:
        entry.update(unnecessary_holds=value, extraction_errors_found_in_review=value, reviewer_correction_time=12.5)
    return data


def test_results_flag_fails_on_null_result_fields():
    data = complete()
    result = failures(data, results=True)
    for key in ("unnecessary_holds", "extraction_errors_found_in_review", "reviewer_correction_time"):
        assert sum(f"result {key} is not recorded" in failure for failure in result) == 3
    assert failures(data) == []


def test_results_flag_passes_when_results_are_filled():
    assert failures(with_results(complete()), results=True) == []


def test_results_apply_no_numeric_threshold():
    assert failures(with_results(complete(), value=40), results=True) == []


def test_results_must_be_non_negative_numbers():
    data = with_results(complete())
    data["acceptance"][0]["unnecessary_holds"] = -1
    data["acceptance"][0]["reviewer_correction_time"] = "ten minutes"
    result = failures(data, results=True)
    assert any("unnecessary_holds must be a non-negative number" in f for f in result)
    assert any("reviewer_correction_time must be a non-negative number" in f for f in result)


def test_results_command_line_flag(tmp_path):
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps(complete()), encoding="utf-8")
    assert check_checklist.main([str(path), "--results"]) == 1
    path.write_text(json.dumps(with_results(complete())), encoding="utf-8")
    assert check_checklist.main([str(path), "--results"]) == 0


# Shape ---------------------------------------------------------------------------------------------

def test_non_object_and_non_list_sections_fail():
    assert failures([]) == ["the checklist must be a JSON object"]
    data = complete()
    data["walkthrough"] = {}
    assert "walkthrough must be a list" in failures(data)
