"""The extraction gate, shared by check-gate and stage-drafts (Task 5.1).

Requirements 2.1, 2.3, 6.5. Extraction may proceed for a registered version
only when its recorded assessment result is non_critical or a reviewer has
recorded clearance for that exact version. Clearance on another version of the
same Drive file never counts.
"""

from dataclasses import dataclass

from staging_lib import registry


@dataclass(frozen=True)
class GateResult:
    cleared: bool
    reason: str
    source: object = None  # registry.SourcePdf when the version is registered


def check_gate(connection, drive_file_id, file_hash):
    """Return a GateResult for one exact version. Reads only."""
    label = f"{drive_file_id} with file_hash {file_hash}"
    source = registry.find_version(connection, drive_file_id, file_hash)
    if source is None:
        return GateResult(False, f"unknown version: {label} is not registered; run risk-assess for it first")
    row = connection.execute(
        "SELECT risk_decision, clearance_by FROM processing_status WHERE pdf_id = ?", (source.pdf_id,)
    ).fetchone()
    if row is None or row[0] is None:
        return GateResult(False, f"no assessment result recorded for {label}; run risk-assess first", source)
    decision, clearance_by = row
    if decision == "non_critical":
        return GateResult(True, "non_critical assessment result", source)
    if clearance_by:
        return GateResult(True, f"cleared by {clearance_by}", source)
    return GateResult(
        False,
        f"held pending clearance: {label} has assessment result {decision} and no reviewer clearance; "
        "a lab-authorized reviewer must clear it in the review app",
        source,
    )
