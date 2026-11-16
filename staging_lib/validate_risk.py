"""Risk packet validation (Task 3.2, Requirement 21.4)."""

DECISIONS = ("non_critical", "critical", "uncertain")


def validate_risk(packet):
    """Return a descriptive error string, or None when the risk fields are valid."""
    decision = packet.get("decision")
    if decision not in DECISIONS:
        return f"decision must be one of {', '.join(DECISIONS)}; got {decision!r}"
    issues = packet.get("issues")
    if not isinstance(issues, list):
        return "issues must be an array (use [] when no issues were found)"
    for number, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            return f"issue {number} must be an object"
        reason = issue.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return f"issue {number} needs a non-empty reason"
        if "source_location" not in issue:
            return f"issue {number} needs source_location (an object, or null when unknown)"
        location = issue["source_location"]
        if location is not None and not isinstance(location, dict):
            return f"issue {number} source_location must be an object or null"
    return None
