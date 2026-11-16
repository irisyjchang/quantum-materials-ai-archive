"""Result ordering and display (Task 21.2, Requirements 17.4, 17.5, 19.2, 20.1, 20.2).

Chronological, oldest first. Within a month, a month-only date (2018-10) comes
before day dates (2018-10-05). Runs without a date come last. On the same date,
runs with a JC number come first, ordered by JC number then run_id (so runs
sharing a JC number are ordered by run_id); runs without a JC number follow,
ordered by researcher name then run_id.
"""

import json


def _jc_key(jc):
    digits = jc.strip()
    return (0, int(digits), digits) if digits.isdigit() else (1, 0, digits.lower())


def sort_key(result):
    date = result["growth_date"]
    date_key = (1, "", 0, "") if not date else (0, date[:7], len(date), date)
    jc = result["jc_number"]
    if jc:
        within = (0, _jc_key(jc), "", result["run_id"])
    else:
        within = (1, (0, 0, ""), (result["researcher_name"] or "").lower(), result["run_id"])
    return date_key + within


def ordered(results):
    return sorted(results, key=sort_key)


def display(result):
    """Add display fields: locations, composition text. Dates are shown exactly as stored (no invented day)."""
    try:
        locations = json.loads(result["source_locations_json"] or "[]")
    except json.JSONDecodeError:
        locations = []
    try:
        composition = json.loads(result["composition_json"]) if result["composition_json"] else None
    except json.JSONDecodeError:
        composition = result["composition_json"]
    formula = composition.get("formula") if isinstance(composition, dict) else None
    return {**result, "locations": [loc for loc in locations if isinstance(loc, dict)],
            "composition_text": formula or (json.dumps(composition, ensure_ascii=False) if composition else None)}
