"""Queries for the processing status view (Task 11.1, Requirements 14.1, 14.2, 14.3, 14.7, 10.4).

Everything is read fresh on each request, so counts reflect every reviewer action.
"""

import json
from dataclasses import dataclass, field

RISK_TIERS = {"non_critical": "Non-critical", "critical": "Critical", "uncertain": "Uncertain"}
STATUS_LABELS = {
    "risk_assessed": "Assessed, ready for extraction",
    "held_pending_clearance": "Held pending clearance",
    "cleared": "Cleared for extraction",
    "extraction_complete": "Extraction complete",
    "technical_failure": "Technical failure",
}
REVIEW_STATUSES = {"Approved": "approved", "Pending review": "pending", "Held": "held"}


@dataclass
class HeldDraft:
    draft_id: str
    hold_reason: str
    locations: list


@dataclass
class PdfStatus:
    pdf_id: str
    archive_filename: str
    drive_file_id: str
    file_hash: str
    status: object
    risk_decision: object
    reason: object
    issues: list
    clearance_by: object
    clearance_at: object
    updated_at: object
    counts: dict = field(default_factory=lambda: {"approved": 0, "pending": 0, "held": 0})
    held_drafts: list = field(default_factory=list)
    reserved: bool = False

    @property
    def risk_tier(self):
        return RISK_TIERS.get(self.risk_decision, "Not assessed")

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, "No status recorded")

    @property
    def draft_total(self):
        return sum(self.counts.values())

    @property
    def reached_extraction(self):
        return self.status == "extraction_complete" or self.draft_total > 0

    @property
    def counts_summary(self):
        return (f"{self.counts['approved']} approved · {self.counts['pending']} pending · "
                f"{self.counts['held']} held")


def _parse_issues(text):
    if not text:
        return []
    try:
        issues = json.loads(text)
    except json.JSONDecodeError:
        return [{"reason": text, "source_location": None}]
    return issues if isinstance(issues, list) else []


def _locations(text):
    try:
        locations = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return []
    return [loc for loc in locations if isinstance(loc, dict)] if isinstance(locations, list) else []


def pdf_statuses(connection, reserved_ids=frozenset()):
    """One PdfStatus per registered source PDF version, newest activity first within a filename."""
    rows = connection.execute(
        "SELECT s.pdf_id, s.archive_filename, s.drive_file_id, s.file_hash, p.status, p.risk_decision,"
        " p.reason, p.issues_json, p.clearance_by, p.clearance_at, p.updated_at"
        " FROM source_pdfs AS s LEFT JOIN processing_status AS p ON p.pdf_id = s.pdf_id"
        " ORDER BY s.archive_filename, p.updated_at DESC, s.pdf_id"
    ).fetchall()
    statuses = {}
    for row in rows:
        (pdf_id, filename, drive_file_id, file_hash, status, decision, reason, issues_json,
         clearance_by, clearance_at, updated_at) = row
        statuses[pdf_id] = PdfStatus(
            pdf_id, filename, drive_file_id, file_hash, status, decision, reason, _parse_issues(issues_json),
            clearance_by, clearance_at, updated_at, reserved=drive_file_id in reserved_ids,
        )

    for pdf_id, review_status, count in connection.execute(
        "SELECT pdf_id, review_status, count(*) FROM draft_runs GROUP BY pdf_id, review_status"
    ):
        key = REVIEW_STATUSES.get(review_status)
        if pdf_id in statuses and key:
            statuses[pdf_id].counts[key] = count

    for draft_id, pdf_id, hold_reason, locations in connection.execute(
        "SELECT draft_id, pdf_id, hold_reason, source_locations_json FROM draft_runs"
        " WHERE review_status = 'Held' ORDER BY updated_at, draft_id"
    ):
        if pdf_id in statuses:
            statuses[pdf_id].held_drafts.append(HeldDraft(draft_id, hold_reason, _locations(locations)))

    return list(statuses.values())
