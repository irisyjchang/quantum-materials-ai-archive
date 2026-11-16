"""Tests for the Test checklist validator (Task 24.3).

Requirements 27.1, 27.2, 27.7 to 27.10, 28.1 to 28.3, 28.8, 28.12, 28.14.
Synthetic checklists with placeholder IDs only; no lab PDFs are named.
"""

import copy
import json
from pathlib import Path

import pytest

from tools import check_checklist
from tools.check_checklist import CRITICAL_CASES, MISSING_INFORMATION_CASES, STRUCTURAL_CASES, check

ROOT = Path(__file__).resolve().parents[1]


def placeholder_hash(number):
    return f"{number:064x}"


def pdf(number, binder=1, **fields):
    return {"filename": f"log-{binder}-{number:03d}.pdf", "drive_file_id": f"placeholder-drive-{number}",
            "file_hash": placeholder_hash(number), **fields}


def expected_run(row, status="approve"):
    run = {"source_page": 1, "source_row": row, "researcher_name": "Placeholder", "growth_date": "2018-10",
           "jc_number": None, "stoichiometry": "MoSe2", "expected_status": status}
    if status == "approve":
        run["search_terms"] = {"month": "2018-10", "name": "Placeholder"}
    else:
        run["hold_reason"] = "ratio unclear"
    return run


def acceptance(number, **fields):
    entry = pdf(number, binder=2, expected_risk_tier="non_critical", expected_hold_stage=None,
                expected_hold_reason=None, expected_run_count=2, expected_runs=[expected_run(1), expected_run(2)],
                expected_recorded_by="Placeholder Reviewer", expected_recorded_at="2026-11-01T09:00:00+00:00",
                first_run_at=None, unnecessary_holds=None, extraction_errors_found_in_review=None,
                reviewer_correction_time=None)
    entry.update(fields)
    return entry


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
    walkthrough[2]["one_critical_run"] = True
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


# Template ------------------------------------------------------------------------------------------

def test_repository_template_names_no_pdfs_and_fails_with_missing_items(capsys):
    path = ROOT / "test_checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["walkthrough"] == [] and data["acceptance"] == []
    assert set(data["tool_versions"]) == {"skill", "staging_tool", "review_app"}
    assert set(data["entry_templates"]["acceptance_pdf"]) >= {
        "expected_risk_tier", "expected_hold_reason", "expected_run_count", "expected_runs",
        "expected_recorded_by", "expected_recorded_at", "expected_hold_stage", "first_run_at",
        "unnecessary_holds", "extraction_errors_found_in_review", "reviewer_correction_time"}
    assert check_checklist.main([str(path)]) == 1
    output = capsys.readouterr().out
    assert "is not ready" in output
    for expected in ("no PDF from Binder 1", "missing_researcher_name", "(a) no_usable_lookup_value",
                     "one_critical_run", "clear_single_run", "has_furnace_layout_sketch",
                     "tool_versions.skill", "before_extraction"):
        assert expected in output


def test_template_allowed_values_match_the_validator():
    allowed = json.loads((ROOT / "test_checklist.json").read_text(encoding="utf-8"))["entry_templates"]["allowed_values"]
    assert tuple(allowed["missing_information_cases"]) == MISSING_INFORMATION_CASES
    assert tuple(allowed["structural_cases"]) == STRUCTURAL_CASES
    assert {name: letter for letter, name in allowed["critical_case"].items()} == CRITICAL_CASES


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


# Identity and overlap (27.1, 28.1, 28.3) -----------------------------------------------------------

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
    assert any("reserved for the acceptance run" in failure for failure in failures(data))
    assert any("reserved for the acceptance run" in failure for failure in failures(data, walkthrough_only=True))


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

@pytest.mark.parametrize("case", MISSING_INFORMATION_CASES)
def test_each_missing_information_case_is_required(case):
    data = complete()
    for entry in data["walkthrough"]:
        if case in entry.get("missing_information_cases", []):
            entry["missing_information_cases"].remove(case)
    assert f"walkthrough: missing-information case {case} is not covered (Requirement 27.2)" in failures(data)


def test_missing_information_case_on_a_critical_pdf_does_not_count():
    data = complete()
    data["walkthrough"][0]["missing_information_cases"].remove("missing_researcher_name")
    critical_entry(data, "missing_stoichiometry")["missing_information_cases"] = ["missing_researcher_name"]
    report = check(data)
    assert any("missing_researcher_name is not covered" in failure for failure in report.failures)
    assert any("are not counted" in warning for warning in report.warnings)


@pytest.mark.parametrize("case", list(CRITICAL_CASES))
def test_each_critical_case_is_required(case):
    data = complete()
    data["walkthrough"].remove(critical_entry(data, case))
    if not any(entry.get("one_critical_run") for entry in data["walkthrough"]):
        data["walkthrough"][3]["one_critical_run"] = True
    message = (f"walkthrough: critical case ({CRITICAL_CASES[case]}) {case} has no dedicated PDF or waiver "
               "(Requirement 27.8)")
    assert failures(data) == [message]


def test_entry_naming_two_critical_cases_counts_for_neither():
    data = complete()
    first = critical_entry(data, "ambiguous_compound")
    data["walkthrough"].remove(critical_entry(data, "ambiguous_ratio"))
    first["critical_case"] = ["ambiguous_compound", "ambiguous_ratio"]
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
        entry.pop("one_critical_run", None)
    assert failures(data) == ["walkthrough: no multi-run PDF flagged one_critical_run: true (Requirement 27.9)"]


def test_one_critical_run_flag_without_a_critical_case_fails():
    data = complete()
    data["walkthrough"][0]["one_critical_run"] = True
    assert any("one_critical_run needs the PDF's critical_case" in failure for failure in failures(data))


@pytest.mark.parametrize("case", STRUCTURAL_CASES)
def test_each_structural_case_is_required(case):
    data = complete()
    for entry in data["walkthrough"]:
        if case in entry.get("structural_cases", []):
            entry["structural_cases"].remove(case)
    assert failures(data) == [f"walkthrough: structural case {case} is not covered (Requirement 27.10)"]


def test_no_layout_sketch_pdf_fails():
    data = complete()
    data["walkthrough"][0]["has_furnace_layout_sketch"] = False
    assert failures(data) == ["walkthrough: no PDF flagged has_furnace_layout_sketch: true (Requirement 27.7)"]


def test_layout_sketch_on_a_critical_pdf_does_not_count():
    data = complete()
    data["walkthrough"][0]["has_furnace_layout_sketch"] = False
    critical_entry(data, "ambiguous_ratio")["has_furnace_layout_sketch"] = True
    assert "walkthrough: no PDF flagged has_furnace_layout_sketch: true (Requirement 27.7)" in failures(data)


# Acceptance (28.2, 28.8, 28.12) --------------------------------------------------------------------

def test_missing_tool_versions_fails():
    data = complete()
    del data["tool_versions"]
    assert any(failure.startswith("tool_versions is missing") for failure in failures(data))


@pytest.mark.parametrize("key", ["skill", "staging_tool", "review_app"])
def test_incomplete_tool_versions_fail(key):
    data = complete()
    data["tool_versions"][key] = None
    assert failures(data) == [f"tool_versions.{key} is not recorded (Requirement 28.12)"]


def test_walkthrough_only_skips_acceptance_checks():
    data = complete()
    del data["tool_versions"]
    data["acceptance"] = [{"drive_file_id": "placeholder-drive-999"}]
    assert failures(data, walkthrough_only=True) == []


def test_no_before_extraction_entry_fails():
    data = complete()
    del data["acceptance"][1]
    assert failures(data) == ["acceptance: no entry has expected_hold_stage before_extraction (Requirement 28.8)"]


@pytest.mark.parametrize("key,value", [
    ("expected_risk_tier", None), ("expected_run_count", None), ("expected_runs", None),
])
def test_acceptance_entry_without_expected_outcome_fails(key, value):
    data = complete()
    data["acceptance"][0][key] = value
    assert any("no expected outcome" in failure for failure in failures(data))


def test_expected_runs_must_match_the_run_count_and_name_page_and_row():
    data = complete()
    data["acceptance"][0]["expected_run_count"] = 3
    data["acceptance"][0]["expected_runs"][0]["source_row"] = None
    result = failures(data)
    assert any("lists 2 runs but expected_run_count is 3" in f for f in result)
    assert any("source_row must be a whole number" in f for f in result)


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
    assert any(key in failure for failure in failures(data))


def test_expected_recorded_at_without_time_zone_fails():
    data = complete()
    data["acceptance"][0]["expected_recorded_at"] = "2026-11-01T09:00:00"
    assert any("with a time zone" in failure for failure in failures(data))


def test_expected_recorded_after_first_run_fails():
    data = complete()
    data["acceptance"][0]["first_run_at"] = "2026-10-31T09:00:00+00:00"
    assert any("later than first_run_at" in failure for failure in failures(data))
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
