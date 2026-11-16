"""Tests for the reviewer dropdown and the recorded-action guard (Task 10.4, Requirements 7.1 to 7.4).

The real action routes arrive in Tasks 12, 14, 15, and 17; each uses
require_confirmed_reviewer. Here a test-only route stands in for them and
writes one row only when the guard allows it. Reviewer names are temporary
placeholders in a temporary config; the repository's config.json is not used.
"""

import hashlib
import json
from pathlib import Path

import pytest
from flask import render_template_string

from conftest import query
from db.init_db import initialize
from review_app.app import AppStartupError, create_app
from review_app.reviewers import require_confirmed_reviewer

NAMES = ["Placeholder Reviewer A", "Placeholder Reviewer B"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_config(path, reviewers):
    path.write_text(json.dumps({"reviewers": reviewers, "backup_folder": None, "backup_name_pattern": None}),
                    encoding="utf-8")
    return path


def build_app(tmp_path, reviewers=NAMES):
    initialize(tmp_path / "test.sqlite")
    config = write_config(tmp_path / "config.json", reviewers)
    app = create_app("test", root=tmp_path, config_path=config)

    @app.route("/_test/form")
    def demo_form():
        return render_template_string(
            '{% extends "base.html" %}{% block content %}'
            '<form method="post" action="/_test/action">{% include "_reviewer.html" %}</form>'
            '{% endblock %}')

    @app.route("/_test/action", methods=["POST"])
    def demo_action():
        from review_app.app import get_db
        reviewer, response = require_confirmed_reviewer("hold this draft")
        if response is not None:
            return response
        db = get_db()
        db.execute("INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash)"
                   " VALUES ('recorded', ?, 'placeholder-drive-id', 'placeholder-hash')", (reviewer,))
        db.commit()
        return "recorded"

    return app, tmp_path / "test.sqlite", config


def recorded(database):
    return query(database, "SELECT archive_filename FROM source_pdfs WHERE pdf_id = 'recorded'")


# Dropdown (7.1, 7.4) ------------------------------------------------------------------

def test_dropdown_lists_exactly_the_configured_names(tmp_path):
    app, _, _ = build_app(tmp_path)
    page = app.test_client().get("/_test/form").get_data(as_text=True)
    assert '<option value="">Select your name</option>' in page
    for name in NAMES:
        assert f'<option value="{name}">{name}</option>' in page
    assert page.count("<option") == len(NAMES) + 1
    assert 'name="reviewer" required' in page


def test_empty_reviewer_list_disables_the_dropdown(tmp_path):
    app, _, _ = build_app(tmp_path, reviewers=[])
    page = app.test_client().get("/_test/form").get_data(as_text=True)
    assert "No authorized reviewers configured" in page
    assert 'name="reviewer" disabled' in page


# Refusals write nothing (7.1, 7.3) ------------------------------------------------------

@pytest.mark.parametrize("form", [
    {},
    {"reviewer": ""},
    {"reviewer": "   "},
    {"reviewer": "Someone Not Listed"},
    {"reviewer": "placeholder reviewer a"},
    {"reviewer": "Someone Not Listed", "confirmed": "1"},
    {"confirmed": "1"},
])
def test_missing_or_unknown_name_is_refused_and_nothing_is_written(tmp_path, form):
    app, database, _ = build_app(tmp_path)
    before = digest(database)
    response = app.test_client().post("/_test/action", data=form)
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Select your name" in page and "Nothing was recorded" in page
    assert 'data-environment="test"' in page
    assert recorded(database) == []
    assert digest(database) == before


def test_every_action_is_refused_when_no_reviewers_are_configured(tmp_path):
    app, database, _ = build_app(tmp_path, reviewers=[])
    response = app.test_client().post("/_test/action", data={"reviewer": NAMES[0], "confirmed": "1"})
    assert response.status_code == 400
    assert "No authorized reviewers are configured" in response.get_data(as_text=True)
    assert recorded(database) == []


# Confirmation (7.2) ---------------------------------------------------------------------

def test_valid_name_shows_confirmation_and_writes_nothing(tmp_path):
    app, database, _ = build_app(tmp_path)
    before = digest(database)
    response = app.test_client().post("/_test/action", data={"reviewer": NAMES[1], "hold_reason": "ratio unclear"})
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'You are about to hold this draft as <strong class="confirm-reviewer">{NAMES[1]}</strong>' in page
    assert f'<input type="hidden" name="reviewer" value="{NAMES[1]}">' in page
    assert '<input type="hidden" name="hold_reason" value="ratio unclear">' in page
    assert '<input type="hidden" name="confirmed" value="1">' in page
    assert 'action="/_test/action"' in page
    assert recorded(database) == []
    assert digest(database) == before


def test_confirmed_action_runs_and_records_the_reviewer(tmp_path):
    app, database, _ = build_app(tmp_path)
    response = app.test_client().post("/_test/action", data={"reviewer": f"  {NAMES[0]} ", "confirmed": "1"})
    assert response.status_code == 200
    assert recorded(database) == [(NAMES[0],)]


def test_confirmation_page_escapes_submitted_values(tmp_path):
    app, _, _ = build_app(tmp_path)
    page = app.test_client().post("/_test/action", data={
        "reviewer": NAMES[0], "note": '"><script>alert(1)</script>'}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# Names are read-only (7.4) ---------------------------------------------------------------

def test_config_is_never_written(tmp_path):
    app, _, config = build_app(tmp_path)
    before = config.read_bytes()
    client = app.test_client()
    client.get("/")
    client.get("/_test/form")
    client.post("/_test/action", data={"reviewer": NAMES[0], "confirmed": "1"})
    assert config.read_bytes() == before


def test_reviewer_list_is_immutable_and_no_route_edits_it(tmp_path):
    app, _, _ = build_app(tmp_path)
    assert isinstance(app.config["REVIEWERS"], tuple)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert not any("reviewer" in rule or "config" in rule for rule in rules)


def test_bad_config_stops_startup(tmp_path):
    initialize(tmp_path / "test.sqlite")
    config = write_config(tmp_path / "config.json", ["Same", "Same"])
    with pytest.raises(AppStartupError, match="config problem"):
        create_app("test", root=tmp_path, config_path=config)
