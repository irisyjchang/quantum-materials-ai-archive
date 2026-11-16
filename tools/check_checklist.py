"""Validate the Test checklist (Tasks 24.2, 24.4 to 24.6).

Usage: python tools/check_checklist.py [checklist.json] [--walkthrough-only] [--results]

The path defaults to ``checklist_path`` in config.json, the git-ignored local
checklist test_checklist.local.json. The reserved-PDF guard and the status
view read the same file (Requirement 30.9). Create it from the committed
template with: cp test_checklist.template.json test_checklist.local.json
Exits 0 when the checklist passes and 1 with a list of missing items otherwise.

Walkthrough checks (Requirements 27.1, 27.2, 27.5, 27.7 to 27.10, 27.12 to 27.14, 28.1):
- every PDF entry has filename, drive_file_id, and a 64-character file_hash
  (waiver entries with ``no_example_found: true`` name no PDF)
- no walkthrough PDF shares a filename or drive_file_id with any acceptance
  entry, provisional or confirmed
- the walkthrough has PDFs from Binder 1 and Binder 2 (from ``binder``, or the
  log-<binder>-###.pdf filename)
- each of the nine missing-information cases and five structural cases is
  covered, and at least one PDF has a furnace layout sketch. These count only
  on PDFs without a ``critical_case``, because a held PDF produces no drafts
- each of the ten critical cases (a) to (j) has a PDF whose ``critical_case``
  names that case alone, with expected tier ``critical`` or ``uncertain``
  (``uncertain`` for (j)), or a waiver with a non-empty ``waiver_reason``
- one PDF is flagged ``one_critical_run: true`` (Requirement 27.9)
- every case a PDF claims (including ``furnace_layout_sketch`` and
  ``one_critical_run``) has a ``case_evidence`` item citing page and row, or a
  named area, with the reviewer's observation; ``run_spans_pages`` evidence
  cites at least two pages

Acceptance checks (Requirements 28.2, 28.3, 28.8, 28.12, 28.14 to 28.18):
- every entry has ``reservation_status`` provisional or confirmed, a filename,
  and a drive_file_id (so the guard reserves it)
- with --walkthrough-only nothing more is checked; otherwise every entry must
  be confirmed, ``tool_versions`` must be complete, and each confirmed entry
  must record file_hash and its expected outcomes: tier, run count, and per
  expected run its ``source_locations`` (every page and row), expected values,
  ``blank_or_flagged_fields`` with reasons, and approve or hold status. They are
  recorded by ``expected_recorded_by`` at ``expected_recorded_at``, not later
  than ``first_run_at``. A provisional ``candidate_outcome`` is never an
  expected outcome
- at least one confirmed entry has ``expected_hold_stage: before_extraction``
- with --results, every entry has ``unnecessary_holds``,
  ``extraction_errors_found_in_review``, and ``reviewer_correction_time``
  (minutes). No numeric threshold is applied; tolerances are pending Iris.

The validator checks the lists only. At run time the staging tool's reserved
PDF guard keeps acceptance PDFs out of the walkthrough (Requirement 30).
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import ConfigError, load_config  # noqa: E402
from staging_lib.validate_extraction import FIELD_KEYS  # noqa: E402

TEMPLATE_NAME = "test_checklist.template.json"
MISSING_INFORMATION_CASES = (
    "missing_researcher_name",
    "missing_growth_date_with_timestamp",
    "missing_growth_date_without_timestamp",
    "missing_jc_number",
    "missing_furnace_cycle_detail",
    "missing_furnace_layout",
    "missing_or_unclear_growth_process",
    "missing_timestamp",
    "missing_optional_measurement",
)
CRITICAL_CASES = {
    "no_usable_lookup_value": "a",
    "missing_stoichiometry": "b",
    "ambiguous_compound": "c",
    "ambiguous_ratio": "d",
    "ambiguous_composition_unit": "e",
    "overwritten_composition_digit": "f",
    "unclear_element_symbol": "g",
    "unknown_ratio_basis": "h",
    "uncertain_row_or_run_label": "i",
    "cannot_be_reliably_assessed": "j",
}
UNCERTAIN_ONLY = {"cannot_be_reliably_assessed"}
STRUCTURAL_CASES = (
    "clear_single_run",
    "multi_run_all_eligible",
    "run_spans_pages",
    "carried_down_compound",
    "entries_in_both_tables",
)
LAYOUT_SKETCH_CASE = "furnace_layout_sketch"
ONE_CRITICAL_RUN_CASE = "one_critical_run"
SPANS_PAGES_CASE = "run_spans_pages"
RISK_TIERS = ("non_critical", "critical", "uncertain")
HOLD_STAGES = ("before_extraction", "in_review")
RUN_STATUSES = ("approve", "hold")
RESERVATION_STATUSES = ("provisional", "confirmed")
TOOL_VERSION_KEYS = ("skill", "staging_tool", "review_app")
RESULT_KEYS = ("unnecessary_holds", "extraction_errors_found_in_review", "reviewer_correction_time")
SEARCH_TERM_KEYS = ("month", "name", "date", "jc")
EXPECTED_VALUE_KEYS = ("researcher_name", "growth_date", "jc_number", "stoichiometry")
LOOKUP_KEYS = ("researcher_name", "growth_date", "jc_number")
# Extraction field whose blank expectation requires a null expected value, and that value's key.
VALUE_FOR_FIELD = {"researcher_name": "researcher_name", "growth_date": "growth_date",
                   "jc_number": "jc_number", "composition": "stoichiometry"}
FIELD_EXPECTATIONS = {
    "blank": ("missing", "omitted"),
    "flagged": ("inferred", "derived", "unreadable", "ambiguous"),
}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_BINDER_FILENAME = re.compile(r"^log-(\d+)-\d+\.pdf$")


@dataclass
class Report:
    failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.failures


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive(value):
    return _count(value) and value >= 1


def _time(value):
    """A timezone-aware datetime from an ISO 8601 string, else None."""
    if not _text(value):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _label(section, index, entry):
    name = entry.get("filename") if isinstance(entry, dict) else None
    return f"{section}[{index}]" + (f" {name}" if _text(name) else "")


def _string_list(entry, key, allowed, label, report):
    values = entry.get(key, [])
    if values is None:
        return []
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        report.failures.append(f"{label}: {key} must be a list of case names")
        return []
    for value in values:
        if value not in allowed:
            report.failures.append(f"{label}: unknown {key} value {value!r}")
    return [value for value in values if value in allowed]


def _critical_names(entry, label, report):
    value = entry.get("critical_case")
    if value is None:
        return []
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        report.failures.append(f"{label}: critical_case must be one critical case name")
        return []
    for name in names:
        if name not in CRITICAL_CASES:
            report.failures.append(f"{label}: unknown critical_case {name!r}")
    return names


def _check_identity(entry, label, report, need_hash=True):
    for key in ("filename", "drive_file_id"):
        if not _text(entry.get(key)):
            report.failures.append(f"{label}: missing {key}")
    file_hash = entry.get("file_hash")
    if not _text(file_hash):
        if need_hash:
            report.failures.append(f"{label}: missing file_hash")
    elif not _HASH.match(file_hash):
        report.failures.append(f"{label}: file_hash must be the 64-character lowercase SHA-256 of the PDF version")


def _binder(entry):
    binder = entry.get("binder")
    if isinstance(binder, int) and not isinstance(binder, bool):
        return binder
    if isinstance(binder, str) and binder.strip().isdigit():
        return int(binder)
    match = _BINDER_FILENAME.match(entry.get("filename") or "")
    return int(match.group(1)) if match else None


def location_problems(location, allow_area=True):
    """Problems with one {pdf_index, row} source location (row may be null with an area when allowed)."""
    if not isinstance(location, dict):
        return ["a source location must be a JSON object with pdf_index and row"]
    problems = []
    if not _positive(location.get("pdf_index")):
        problems.append("pdf_index must be a whole number of at least 1")
    row = location.get("row")
    if row is None and allow_area:
        if not _text(location.get("area")):
            problems.append("row is null, so name the area (for example shared header)")
    elif not _positive(row):
        problems.append("row must be a whole number of at least 1" + (" or null with an area" if allow_area else ""))
    return problems


def check_evidence(entry, claimed, label, report):
    """Requirements 27.12 and 27.14: each claimed case cites its source location and observation."""
    items = entry.get("case_evidence", [])
    if items is None:
        items = []
    if not isinstance(items, list):
        report.failures.append(f"{label}: case_evidence must be a list")
        return
    cited = set()
    for number, item in enumerate(items, 1):
        where = f"{label} case_evidence[{number}]"
        if not isinstance(item, dict):
            report.failures.append(f"{where}: must be a JSON object")
            continue
        case = item.get("case")
        if case not in claimed:
            report.failures.append(f"{where}: case {case!r} is not one this entry claims")
            continue
        cited.add(case)
        locations = item.get("source_locations")
        if not isinstance(locations, list) or not locations:
            report.failures.append(f"{where}: source_locations must list at least one page and row (or area)")
        else:
            for position, location in enumerate(locations, 1):
                for problem in location_problems(location):
                    report.failures.append(f"{where} source_locations[{position}]: {problem}")
            pages = {location.get("pdf_index") for location in locations if isinstance(location, dict)}
            if case == SPANS_PAGES_CASE and len(pages) < 2:
                report.failures.append(f"{where}: run_spans_pages evidence must cite at least two pages "
                                       "(Requirement 27.14)")
        for key in ("observation", "observed_by"):
            if not _text(item.get(key)):
                report.failures.append(f"{where}: {key} is not recorded")
    for case in sorted(claimed - cited):
        report.failures.append(f"{label}: no case_evidence for {case}; cite the page and row (or area) and the "
                               "observation that qualifies this PDF (Requirement 27.12)")


def check_walkthrough(entries, acceptance_filenames, acceptance_ids, report):
    binders, missing_cases, structural_cases = set(), set(), set()
    covered_critical, layout_sketch, one_critical_run = set(), False, False
    for index, entry in enumerate(entries):
        label = _label("walkthrough", index, entry)
        if not isinstance(entry, dict):
            report.failures.append(f"{label}: entry must be a JSON object")
            continue
        names = _critical_names(entry, label, report)
        if entry.get("no_example_found") is True:
            if len(names) != 1 or names[0] not in CRITICAL_CASES:
                report.failures.append(f"{label}: a waiver must name exactly one critical_case")
            elif not _text(entry.get("waiver_reason")):
                report.failures.append(f"{label}: waiver for critical case ({CRITICAL_CASES[names[0]]}) "
                                       f"{names[0]} needs a waiver_reason")
            else:
                covered_critical.add(names[0])
            continue

        _check_identity(entry, label, report)
        filename, drive_file_id = entry.get("filename"), entry.get("drive_file_id")
        if _text(filename) and filename.strip() in acceptance_filenames:
            report.failures.append(f"{label}: filename {filename} matches an acceptance entry (provisional or "
                                   "confirmed); it is reserved for the acceptance run (Requirement 27.13)")
        if _text(drive_file_id) and drive_file_id.strip() in acceptance_ids:
            report.failures.append(f"{label}: drive_file_id {drive_file_id} matches an acceptance entry "
                                   "(provisional or confirmed); it is reserved for the acceptance run "
                                   "(Requirement 27.13)")
        binder = _binder(entry)
        if binder is None:
            report.failures.append(f"{label}: binder unknown; set binder or use a log-<binder>-###.pdf filename")
        else:
            binders.add(binder)
        missing = _string_list(entry, "missing_information_cases", MISSING_INFORMATION_CASES, label, report)
        structural = _string_list(entry, "structural_cases", STRUCTURAL_CASES, label, report)
        sketch = entry.get("has_furnace_layout_sketch") is True
        flagged_one = entry.get("one_critical_run") is True

        claimed = set(missing) | set(structural)
        claimed |= {name for name in names if name in CRITICAL_CASES}
        if sketch:
            claimed.add(LAYOUT_SKETCH_CASE)
        if flagged_one:
            claimed.add(ONE_CRITICAL_RUN_CASE)
        check_evidence(entry, claimed, label, report)

        if names:
            tier = entry.get("expected_tier")
            if len(names) > 1:
                report.failures.append(f"{label}: names more than one critical case ({', '.join(names)}); a "
                                       "critical-case PDF must carry one case, so it counts for none")
            elif names[0] in CRITICAL_CASES:
                allowed = ("uncertain",) if names[0] in UNCERTAIN_ONLY else ("critical", "uncertain")
                if tier not in allowed:
                    report.failures.append(f"{label}: expected_tier for {names[0]} must be "
                                           + " or ".join(allowed))
                else:
                    covered_critical.add(names[0])
            if flagged_one:
                one_critical_run = True
            if missing or structural or sketch:
                report.warnings.append(f"{label}: missing-information, structural, and layout-sketch cases on a "
                                       "critical-case PDF are not counted, because the PDF is held before drafts")
            continue

        if flagged_one:
            report.failures.append(f"{label}: one_critical_run needs the PDF's critical_case and expected_tier")
        missing_cases.update(missing)
        structural_cases.update(structural)
        layout_sketch = layout_sketch or sketch

    for binder in (1, 2):
        if binder not in binders:
            report.failures.append(f"walkthrough: no PDF from Binder {binder} (Requirement 27.1)")
    for case in MISSING_INFORMATION_CASES:
        if case not in missing_cases:
            report.failures.append(f"walkthrough: missing-information case {case} is not covered (Requirement 27.2)")
    for case, letter in CRITICAL_CASES.items():
        if case not in covered_critical:
            report.failures.append(f"walkthrough: critical case ({letter}) {case} has no dedicated PDF or waiver "
                                   "(Requirement 27.8)")
    if not one_critical_run:
        report.failures.append("walkthrough: no multi-run PDF flagged one_critical_run: true (Requirement 27.9)")
    for case in STRUCTURAL_CASES:
        if case not in structural_cases:
            report.failures.append(f"walkthrough: structural case {case} is not covered (Requirement 27.10)")
    if not layout_sketch:
        report.failures.append("walkthrough: no PDF flagged has_furnace_layout_sketch: true (Requirement 27.7)")


def _check_source_locations(run, label, report):
    for old in ("source_page", "source_row"):
        if old in run:
            report.failures.append(f"{label}: {old} is replaced by source_locations, a list of "
                                   "{pdf_index, row} for every page and row the run occupies")
    locations = run.get("source_locations")
    if not isinstance(locations, list) or not locations:
        report.failures.append(f"{label}: source_locations must list every page and row the run occupies "
                               "(Requirement 28.2)")
        return
    seen = set()
    for position, location in enumerate(locations, 1):
        problems = location_problems(location, allow_area=False)
        for problem in problems:
            report.failures.append(f"{label} source_locations[{position}]: {problem}")
        if not problems:
            key = (location["pdf_index"], location["row"])
            if key in seen:
                report.failures.append(f"{label} source_locations[{position}]: page {key[0]}, row {key[1]} "
                                       "is listed twice")
            seen.add(key)


def _check_blank_or_flagged(run, label, report):
    """Returns {field: expectation} for the run's blank_or_flagged_fields (Requirement 28.2)."""
    items = run.get("blank_or_flagged_fields")
    if not isinstance(items, list):
        report.failures.append(f"{label}: record blank_or_flagged_fields (an empty list when no field should "
                               "stay blank or be flagged)")
        return {}
    expectations = {}
    for number, item in enumerate(items, 1):
        where = f"{label} blank_or_flagged_fields[{number}]"
        if not isinstance(item, dict):
            report.failures.append(f"{where}: must be a JSON object")
            continue
        name, expectation = item.get("field"), item.get("expectation")
        if name not in FIELD_KEYS:
            report.failures.append(f"{where}: field must be one of {', '.join(FIELD_KEYS)}")
            continue
        if name in expectations:
            report.failures.append(f"{where}: field {name} is listed more than once")
            continue
        if expectation not in FIELD_EXPECTATIONS:
            report.failures.append(f"{where}: expectation must be blank or flagged")
            continue
        expectations[name] = expectation
        if not _text(item.get("reason")):
            report.failures.append(f"{where}: give the reason {name} should be {expectation}")
        status = item.get("expected_field_status")
        if status is not None and status not in FIELD_EXPECTATIONS[expectation]:
            report.failures.append(f"{where}: expected_field_status for a {expectation} field must be "
                                   + " or ".join(FIELD_EXPECTATIONS[expectation]))
        if item.get("source_location") is not None:
            for problem in location_problems(item["source_location"]):
                report.failures.append(f"{where} source_location: {problem}")
        value_key = VALUE_FOR_FIELD.get(name)
        if expectation == "blank" and value_key and run.get(value_key) is not None:
            report.failures.append(f"{where}: {name} is expected blank, so {value_key} must be null")
    return expectations


def _check_expected_run(run, label, report):
    if not isinstance(run, dict):
        report.failures.append(f"{label}: each expected run must be a JSON object")
        return None
    _check_source_locations(run, label, report)
    for key in EXPECTED_VALUE_KEYS:
        if key not in run:
            report.failures.append(f"{label}: record {key} (null when not readable)")
    expectations = _check_blank_or_flagged(run, label, report)
    status = run.get("expected_status")
    if status not in RUN_STATUSES:
        report.failures.append(f"{label}: expected_status must be approve or hold")
    if status == "approve":
        terms = run.get("search_terms")
        if not isinstance(terms, dict) or not any(_text(terms.get(key)) for key in SEARCH_TERM_KEYS):
            report.failures.append(f"{label}: an expected-approved run needs search_terms (month, name, date, or jc)")
        if expectations.get("composition") == "blank":
            report.failures.append(f"{label}: an expected-approved run cannot expect composition blank; missing "
                                   "stoichiometry keeps a run on hold")
        if all(run.get(key) is None for key in LOOKUP_KEYS):
            report.failures.append(f"{label}: an expected-approved run needs a researcher_name, growth_date, or "
                                   "jc_number for lookup")
    if status == "hold" and not _text(run.get("hold_reason")):
        report.failures.append(f"{label}: an expected-held run needs a hold_reason")
    return status


def _check_confirmed(entry, label, report):
    """Expected outcomes of one confirmed acceptance entry. Returns (stage, has an expected-held run)."""
    _check_identity(entry, label, report)
    tier = entry.get("expected_risk_tier")
    stage = entry.get("expected_hold_stage")
    held = False
    if tier not in RISK_TIERS:
        report.failures.append(f"{label}: no expected outcome: expected_risk_tier must be " + ", ".join(RISK_TIERS))
    if stage is not None and stage not in HOLD_STAGES:
        report.failures.append(f"{label}: expected_hold_stage must be before_extraction, in_review, or null")
    if stage is not None and not _text(entry.get("expected_hold_reason")):
        report.failures.append(f"{label}: expected_hold_stage {stage} needs an expected_hold_reason")
    if stage == "before_extraction" and tier == "non_critical":
        report.failures.append(f"{label}: a non_critical PDF cannot be expected to stay held before extraction")
    count = entry.get("expected_run_count")
    if not _count(count):
        report.failures.append(f"{label}: no expected outcome: expected_run_count must be a whole number")
    if stage != "before_extraction":
        runs = entry.get("expected_runs")
        if not isinstance(runs, list):
            report.failures.append(f"{label}: no expected outcome: expected_runs must list each run")
        else:
            if _count(count) and len(runs) != count:
                report.failures.append(f"{label}: expected_runs lists {len(runs)} runs but expected_run_count "
                                       f"is {count}")
            statuses = [_check_expected_run(run, f"{label} run {number}", report)
                        for number, run in enumerate(runs, 1)]
            held = "hold" in statuses
            if stage == "in_review" and not held:
                report.failures.append(f"{label}: expected_hold_stage in_review needs a run expected to be held")

    if not _text(entry.get("expected_recorded_by")):
        report.failures.append(f"{label}: expected_recorded_by is not recorded (Requirement 28.18)")
    recorded_at = _time(entry.get("expected_recorded_at"))
    if recorded_at is None:
        report.failures.append(f"{label}: expected_recorded_at must be an ISO 8601 time with a time zone "
                               "(Requirement 28.18)")
    first_run = entry.get("first_run_at")
    if first_run is not None:
        first_run_at = _time(first_run)
        if first_run_at is None:
            report.failures.append(f"{label}: first_run_at must be an ISO 8601 time with a time zone or null")
        elif recorded_at is not None and recorded_at > first_run_at:
            report.failures.append(f"{label}: expected_recorded_at is later than first_run_at; expected outcomes "
                                   "must be recorded before the skill first runs (Requirement 28.18)")
    return stage, held


def check_acceptance(data, entries, results, walkthrough_only, report):
    if not walkthrough_only:
        versions = data.get("tool_versions")
        if not isinstance(versions, dict):
            report.failures.append("tool_versions is missing; record the skill, staging tool, and review app "
                                   "versions (Requirement 28.12)")
        else:
            for key in TOOL_VERSION_KEYS:
                if not _text(versions.get(key)):
                    report.failures.append(f"tool_versions.{key} is not recorded (Requirement 28.12)")

    stages, held_in_review = set(), False
    for index, entry in enumerate(entries):
        label = _label("acceptance", index, entry)
        if not isinstance(entry, dict):
            report.failures.append(f"{label}: entry must be a JSON object")
            continue
        status = entry.get("reservation_status")
        if status not in RESERVATION_STATUSES:
            report.failures.append(f"{label}: reservation_status must be provisional or confirmed (Requirement 28.15)")
        if walkthrough_only or status != "confirmed":
            _check_identity(entry, label, report, need_hash=False)
            if not walkthrough_only and status == "provisional":
                report.failures.append(
                    f"{label} (Drive ID {entry.get('drive_file_id') or 'not recorded'}) is still provisional: a "
                    "reviewer must check the scan, record file_hash and the expected outcomes, then set "
                    "reservation_status to confirmed (Requirements 28.15 to 28.17)")
            continue
        stage, held = _check_confirmed(entry, label, report)
        stages.add(stage)
        held_in_review = held_in_review or held
        if results:
            for key in RESULT_KEYS:
                value = entry.get(key)
                valid = _count(value) if key != "reviewer_correction_time" else (
                    isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0)
                if value is None:
                    report.failures.append(f"{label}: result {key} is not recorded (Requirement 28.14)")
                elif not valid:
                    report.failures.append(f"{label}: result {key} must be a non-negative number")

    if walkthrough_only:
        return
    if "before_extraction" not in stages:
        report.failures.append("acceptance: no confirmed entry has expected_hold_stage before_extraction "
                               "(Requirement 28.8)")
    if stages and not held_in_review:
        report.warnings.append("acceptance: no draft is expected to stay held in review; Requirement 28.8 asks for "
                               "one where the reserved set allows")
    if results and not entries:
        report.failures.append("acceptance: --results needs acceptance entries")


def check(data, results=False, walkthrough_only=False):
    """Validate a parsed checklist and return a Report."""
    report = Report()
    if not isinstance(data, dict):
        report.failures.append("the checklist must be a JSON object")
        return report
    lists = {}
    for section in ("walkthrough", "acceptance"):
        value = data.get(section)
        if not isinstance(value, list):
            report.failures.append(f"{section} must be a list")
            value = []
        lists[section] = value
    accepted = [entry for entry in lists["acceptance"] if isinstance(entry, dict)]
    acceptance_ids = {entry["drive_file_id"].strip() for entry in accepted if _text(entry.get("drive_file_id"))}
    acceptance_filenames = {entry["filename"].strip() for entry in accepted if _text(entry.get("filename"))}
    check_walkthrough(lists["walkthrough"], acceptance_filenames, acceptance_ids, report)
    check_acceptance(data, lists["acceptance"], results, walkthrough_only, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the Test checklist.")
    parser.add_argument("checklist", nargs="?",
                        help="checklist path (default: checklist_path in config.json, the local checklist)")
    parser.add_argument("--walkthrough-only", action="store_true",
                        help="check walkthrough readiness and the reserved-list overlap only (Task 26.1)")
    parser.add_argument("--results", action="store_true",
                        help="also require the per-PDF acceptance results (Requirement 28.14)")
    args = parser.parse_args(argv)
    try:
        path = Path(args.checklist) if args.checklist else load_config().checklist_path
    except ConfigError as error:
        print(f"config problem: {error}", file=sys.stderr)
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"checklist not found: {path}. Create the local checklist from the committed template with: "
              f"cp {TEMPLATE_NAME} {path}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as error:
        print(f"checklist cannot be read: {path}: {error}", file=sys.stderr)
        return 1
    report = check(data, results=args.results, walkthrough_only=args.walkthrough_only)
    for warning in report.warnings:
        print(f"warning: {warning}")
    if report.ok:
        print(f"{path} passes the checklist checks.")
        return 0
    print(f"{path} is not ready ({len(report.failures)} items):")
    for failure in report.failures:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
