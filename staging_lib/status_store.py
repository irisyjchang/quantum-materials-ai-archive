"""processing_status updates from risk-assess (Task 4.4).

Requirements 1.5, 1.6, 1.7, 1.8, 4.1, 5.1, 5.5, 14.8. The staging tool never
writes the clearance fields; only the review app does.
"""

import json
from dataclasses import dataclass

from staging_lib.clock import now_iso

HELD_DECISIONS = ("critical", "uncertain")
KEEP_STATUS_ON_CHANGE = ("cleared", "extraction_complete")


@dataclass(frozen=True)
class StatusResult:
    status: str
    risk_decision: str
    changed: bool


def issues_json(issues):
    """Stored form of the issues array; null when there are no issues."""
    return json.dumps(issues, sort_keys=True, ensure_ascii=False) if issues else None


def held_reason(decision, issues):
    reasons = [issue["reason"].strip() for issue in issues]
    detail = "; ".join(reasons) if reasons else f"assessment result was {decision}"
    return f"Held pending clearance: {detail}"


def status_for_decision(decision):
    return "held_pending_clearance" if decision in HELD_DECISIONS else "risk_assessed"


def recovered_status(decision, clearance_by, has_drafts):
    """Status after a technical failure is resolved (Requirement 14.8)."""
    if has_drafts:
        return "extraction_complete"
    if clearance_by:
        return "cleared"
    return status_for_decision(decision)


def _has_drafts(connection, pdf_id):
    row = connection.execute("SELECT 1 FROM draft_runs WHERE pdf_id = ? LIMIT 1", (pdf_id,)).fetchone()
    return row is not None


def record_assessment(connection, pdf_id, file_hash, decision, issues):
    """Insert or update the processing_status row for one version. Returns a StatusResult."""
    stored_issues = issues_json(issues)
    existing = connection.execute(
        "SELECT status, risk_decision, issues_json, clearance_by FROM processing_status WHERE pdf_id = ?",
        (pdf_id,),
    ).fetchone()

    if existing is None:
        status = status_for_decision(decision)
        reason = held_reason(decision, issues) if status == "held_pending_clearance" else None
        connection.execute(
            "INSERT INTO processing_status (pdf_id, file_hash, status, risk_decision, issues_json,"
            " reason, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pdf_id, file_hash, status, decision, stored_issues, reason, now_iso()),
        )
        return StatusResult(status, decision, True)

    status, old_decision, old_issues, clearance_by = existing
    assessment_changed = decision != old_decision or stored_issues != old_issues

    if status == "technical_failure":
        new_status = recovered_status(decision, clearance_by, _has_drafts(connection, pdf_id))
    elif assessment_changed and status not in KEEP_STATUS_ON_CHANGE:
        new_status = status_for_decision(decision)
    else:
        new_status = status

    if new_status == status and not assessment_changed:
        return StatusResult(status, old_decision, False)

    if new_status == "held_pending_clearance":
        reason = held_reason(decision, issues)
    elif new_status in KEEP_STATUS_ON_CHANGE and new_status == status:
        reason = connection.execute(
            "SELECT reason FROM processing_status WHERE pdf_id = ?", (pdf_id,)
        ).fetchone()[0]
    else:
        reason = None
    connection.execute(
        "UPDATE processing_status SET status = ?, risk_decision = ?, issues_json = ?, reason = ?,"
        " updated_at = ? WHERE pdf_id = ?",
        (new_status, decision, stored_issues, reason, now_iso(), pdf_id),
    )
    return StatusResult(new_status, decision, True)
