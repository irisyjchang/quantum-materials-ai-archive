"""Approval preconditions (Task 16.1, Requirements 8.6, 11.1 to 11.3).

Checked on effective values, both when the approval page is shown and again
on submit, so a hand-made request cannot skip them. Stoichiometry is a hard
gate with no bypass.
"""

from review_app.corrections import valid_growth_date

LOOKUP_FIELDS = ("researcher_name", "growth_date", "jc_number")

# Things the reviewer confirms they checked against the source PDF (design: approval workflow).
VERIFICATIONS = {
    "verified_location": "the source location (page and measurement-table row)",
    "verified_lookup": "at least one lookup value (researcher name, date, or JC number)",
    "verified_stoichiometry": "the stoichiometry",
}


def _present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return True


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def unmet_conditions(fields, locations, integrity):
    """Return the list of unmet approval conditions; empty means the draft may be approved."""
    unmet = []
    if not any(_positive_int(loc.get("pdf_index")) and _positive_int(loc.get("row")) for loc in locations):
        unmet.append("No valid source location: the draft needs at least one page and measurement-table row.")
    if not any(_present(fields[key]["value"]) for key in LOOKUP_FIELDS):
        unmet.append("No lookup value: add a researcher name, growth date, or JC number.")
    date_value = fields["growth_date"]["value"]
    if _present(date_value) and not valid_growth_date(date_value):
        unmet.append("The growth date must be YYYY-MM or YYYY-MM-DD before approval.")
    if not _present(fields["composition"]["value"]):
        unmet.append("No stoichiometry: composition must be filled in and verified before approval.")
    if integrity.blocks_approval:
        unmet.append(f"The source PDF cannot be verified: {integrity.message}")
    return unmet


def missing_verifications(form):
    """The verification boxes the reviewer has not ticked."""
    return [f"Confirm that you verified {label}." for key, label in VERIFICATIONS.items()
            if form.get(key) != "yes"]
