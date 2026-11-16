"""Validate the Test checklist (Task 24.2).

Usage: python tools/check_checklist.py [checklist.json] [--walkthrough-only] [--results]

The path defaults to ``checklist_path`` in config.json (test_checklist.json).
Exits 0 when the checklist passes and 1 with a list of missing items otherwise.

Walkthrough checks (Requirements 27.1, 27.2, 27.5, 27.7 to 27.10, 28.1):
- every entry has filename, drive_file_id, and a 64-character file_hash
  (waiver entries with ``no_example_found: true`` name no PDF)
- no walkthrough drive_file_id is also on the acceptance list
- the walkthrough has PDFs from Binder 1 and Binder 2 (from ``binder``, or the
  log-<binder>-###.pdf filename)
- each of the nine missing-information cases and five structural cases is
  covered, and at least one PDF has a furnace layout sketch. These count only
  on PDFs without a ``critical_case``, because a held PDF produces no drafts
- each of the ten critical cases (a) to (j) has a PDF whose ``critical_case``
  names that case alone, with expected tier ``critical`` or ``uncertain``
  (``uncertain`` for (j)), or a waiver with a non-empty ``waiver_reason``
- one PDF is flagged ``one_critical_run: true`` (Requirement 27.9)

Acceptance checks (Requirements 28.2, 28.3, 28.8, 28.12, 28.14), skipped with --walkthrough-only:
- ``tool_versions`` names the skill, staging tool, and review app versions
- every entry records an expected outcome, ``expected_recorded_by``, and
  ``expected_recorded_at``, and that time is not later than ``first_run_at``
- at least one entry has ``expected_hold_stage: before_extraction``
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
RISK_TIERS = ("non_critical", "critical", "uncertain")
HOLD_STAGES = ("before_extraction", "in_review")
RUN_STATUSES = ("approve", "hold")
TOOL_VERSION_KEYS = ("skill", "staging_tool", "review_app")
RESULT_KEYS = ("unnecessary_holds", "extraction_errors_found_in_review", "reviewer_correction_time")
SEARCH_TERM_KEYS = ("month", "name", "date", "jc")
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


def _check_identity(entry, label, report):
    for key in ("filename", "drive_file_id"):
        if not _text(entry.get(key)):
            report.failures.append(f"{label}: missing {key}")
    file_hash = entry.get("file_hash")
    if not _text(file_hash):
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


def check_walkthrough(entries, acceptance_ids, report):
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
        if _text(entry.get("drive_file_id")) and entry["drive_file_id"].strip() in acceptance_ids:
            report.failures.append(f"{label}: drive_file_id {entry['drive_file_id']} is reserved for the acceptance "
                                   "run and cannot be used in the walkthrough")
        binder = _binder(entry)
        if binder is None:
            report.failures.append(f"{label}: binder unknown; set binder or use a log-<binder>-###.pdf filename")
        else:
            binders.add(binder)
        missing = _string_list(entry, "missing_information_cases", MISSING_INFORMATION_CASES, label, report)
        structural = _string_list(entry, "structural_cases", STRUCTURAL_CASES, label, report)

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
            if entry.get("one_critical_run") is True:
                one_critical_run = True
            if missing or structural or entry.get("has_furnace_layout_sketch") is True:
                report.warnings.append(f"{label}: missing-information, structural, and layout-sketch cases on a "
                                       "critical-case PDF are not counted, because the PDF is held before drafts")
            continue

        if entry.get("one_critical_run") is True:
            report.failures.append(f"{label}: one_critical_run needs the PDF's critical_case and expected_tier")
        missing_cases.update(missing)
        structural_cases.update(structural)
        if entry.get("has_furnace_layout_sketch") is True:
            layout_sketch = True

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


def _check_expected_run(run, label, report):
    if not isinstance(run, dict):
        report.failures.append(f"{label}: each expected run must be a JSON object")
        return None
    for key in ("source_page", "source_row"):
        if not _positive(run.get(key)):
            report.failures.append(f"{label}: {key} must be a whole number of at least 1")
    for key in ("researcher_name", "growth_date", "jc_number", "stoichiometry"):
        if key not in run:
            report.failures.append(f"{label}: record {key} (null when not readable)")
    status = run.get("expected_status")
    if status not in RUN_STATUSES:
        report.failures.append(f"{label}: expected_status must be approve or hold")
    if status == "approve":
        terms = run.get("search_terms")
        if not isinstance(terms, dict) or not any(_text(terms.get(key)) for key in SEARCH_TERM_KEYS):
            report.failures.append(f"{label}: an expected-approved run needs search_terms (month, name, date, or jc)")
    if status == "hold" and not _text(run.get("hold_reason")):
        report.failures.append(f"{label}: an expected-held run needs a hold_reason")
    return status


def check_acceptance(data, entries, results, report):
    versions = data.get("tool_versions")
    if not isinstance(versions, dict):
        report.failures.append("tool_versions is missing; record the skill, staging tool, and review app versions "
                               "(Requirement 28.12)")
    else:
        for key in TOOL_VERSION_KEYS:
            if not _text(versions.get(key)):
                report.failures.append(f"tool_versions.{key} is not recorded (Requirement 28.12)")

    stages = set()
    held_in_review = False
    for index, entry in enumerate(entries):
        label = _label("acceptance", index, entry)
        if not isinstance(entry, dict):
            report.failures.append(f"{label}: entry must be a JSON object")
            continue
        _check_identity(entry, label, report)
        tier = entry.get("expected_risk_tier")
        stage = entry.get("expected_hold_stage")
        if tier not in RISK_TIERS:
            report.failures.append(f"{label}: no expected outcome: expected_risk_tier must be "
                                   + ", ".join(RISK_TIERS))
        if stage is not None and stage not in HOLD_STAGES:
            report.failures.append(f"{label}: expected_hold_stage must be before_extraction, in_review, or null")
        stages.add(stage)
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
                if "hold" in statuses:
                    held_in_review = True
                if stage == "in_review" and "hold" not in statuses:
                    report.failures.append(f"{label}: expected_hold_stage in_review needs a run expected to be held")

        if not _text(entry.get("expected_recorded_by")):
            report.failures.append(f"{label}: expected_recorded_by is not recorded (Requirement 28.2)")
        recorded_at = _time(entry.get("expected_recorded_at"))
        if recorded_at is None:
            report.failures.append(f"{label}: expected_recorded_at must be an ISO 8601 time with a time zone")
        first_run = entry.get("first_run_at")
        if first_run is not None:
            first_run_at = _time(first_run)
            if first_run_at is None:
                report.failures.append(f"{label}: first_run_at must be an ISO 8601 time with a time zone or null")
            elif recorded_at is not None and recorded_at > first_run_at:
                report.failures.append(f"{label}: expected_recorded_at is later than first_run_at; expected outcomes "
                                       "must be recorded before the run (Requirement 28.2)")
        if results:
            for key in RESULT_KEYS:
                value = entry.get(key)
                valid = _count(value) if key != "reviewer_correction_time" else (
                    isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0)
                if value is None:
                    report.failures.append(f"{label}: result {key} is not recorded (Requirement 28.14)")
                elif not valid:
                    report.failures.append(f"{label}: result {key} must be a non-negative number")

    if "before_extraction" not in stages:
        report.failures.append("acceptance: no entry has expected_hold_stage before_extraction (Requirement 28.8)")
    if entries and not held_in_review:
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
    acceptance_ids = {entry["drive_file_id"].strip() for entry in lists["acceptance"]
                      if isinstance(entry, dict) and _text(entry.get("drive_file_id"))}
    check_walkthrough(lists["walkthrough"], acceptance_ids, report)
    if not walkthrough_only:
        check_acceptance(data, lists["acceptance"], results, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the Test checklist.")
    parser.add_argument("checklist", nargs="?", help="checklist path (default: checklist_path in config.json)")
    parser.add_argument("--walkthrough-only", action="store_true",
                        help="check walkthrough coverage and the reserved-list overlap only (Task 26.1)")
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
        print(f"checklist not found: {path}", file=sys.stderr)
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
