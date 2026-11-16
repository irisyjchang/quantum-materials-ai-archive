"""GET /runs: approved-run search (Task 21.3, Requirements 15.1, 15.2, 16.3, 17.3).

Open to anyone at the laptop; no reviewer name is needed to search.
"""

from flask import Blueprint, render_template, request

from review_app.search.ordering import display, ordered
from review_app.search.query import GROWTH_PROCESSES, SearchCriteria, criteria_errors, search

blueprint = Blueprint("search", __name__)


@blueprint.route("/runs")
def search_runs():
    from review_app.app import get_db

    criteria = SearchCriteria.from_args(request.args)
    errors = criteria_errors(criteria)
    results = [] if errors else [display(result) for result in ordered(search(get_db(), criteria))]
    return render_template("search.html", criteria=criteria, errors=errors, results=results,
                           processes=GROWTH_PROCESSES)
