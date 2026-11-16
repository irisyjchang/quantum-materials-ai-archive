"""Search query builder (Task 21.1).

Requirements 15.1 to 15.3, 16.1 to 16.3, 17.1 to 17.3, 18.1, 18.2, 19.1, 19.3.
Search reads growth_runs (joined to source_pdfs for the filename and retained
PDF) and never reads draft_runs, so pending and held drafts cannot appear.
Every criterion can be used alone; given together they must all match (AND).
"""

import re
from dataclasses import dataclass

from review_app.corrections import valid_growth_date

GROWTH_PROCESSES = ("CVT", "Flux Growth", "unclear")
_MONTH = re.compile(r"^\d{4}-\d{2}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class SearchCriteria:
    name: str = ""
    month: str = ""
    date: str = ""
    jc: str = ""
    process: str = "any"

    @classmethod
    def from_args(cls, args):
        get = lambda key: (args.get(key) or "").strip()  # noqa: E731
        return cls(get("name"), get("month"), get("date"), get("jc"), get("process") or "any")

    @property
    def any_criteria(self):
        return bool(self.name or self.month or self.date or self.jc or self.process != "any")


def criteria_errors(criteria):
    errors = []
    if criteria.month and not (_MONTH.match(criteria.month) and valid_growth_date(criteria.month)):
        errors.append("Month must be YYYY-MM, for example 2018-10.")
    if criteria.date and not (_DAY.match(criteria.date) and valid_growth_date(criteria.date)):
        errors.append("Exact date must be YYYY-MM-DD, for example 2018-10-22.")
    if criteria.process != "any" and criteria.process not in GROWTH_PROCESSES:
        errors.append("Growth process must be CVT, Flux Growth, unclear, or any.")
    return errors


def build_query(criteria):
    """Return (sql, parameters) for approved runs matching every given criterion."""
    sql = [
        "SELECT g.run_id, g.pdf_id, g.researcher_name, g.growth_date, g.date_precision, g.jc_number,"
        " g.growth_process, g.composition_json, g.source_locations_json,"
        " s.archive_filename, s.storage_path, s.file_hash"
        " FROM growth_runs AS g JOIN source_pdfs AS s ON s.pdf_id = g.pdf_id"
    ]
    where, params = [], []
    if criteria.name:
        where.append("instr(lower(coalesce(g.researcher_name, '')), lower(?)) > 0")
        params.append(criteria.name)
    if criteria.month:
        where.append("substr(g.growth_date, 1, 7) = ?")
        params.append(criteria.month)
    if criteria.date:
        where.append("g.growth_date = ?")
        params.append(criteria.date)
    if criteria.jc:
        where.append("(g.jc_number = ? OR instr(g.jc_number, ?) > 0)")
        params.extend([criteria.jc, criteria.jc])
    if criteria.process != "any":
        where.append("g.growth_process = ?")
        params.append(criteria.process)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    return "".join(sql), params


def search(db, criteria):
    """Matching approved runs as dicts (unsorted; see ordering.py)."""
    sql, params = build_query(criteria)
    columns = ("run_id", "pdf_id", "researcher_name", "growth_date", "date_precision", "jc_number",
               "growth_process", "composition_json", "source_locations_json", "filename", "storage_path",
               "file_hash")
    return [dict(zip(columns, row)) for row in db.execute(sql, params)]
