"""Reviewer dropdown and the guard for recorded actions (Task 10, Requirements 7.1 to 7.4).

Every recorded action (clearance, correction, hold, approval) takes two steps:

1. The reviewer picks a name from the dropdown and submits the action form.
   An empty or unknown name is refused with HTTP 400 and nothing is written.
2. The app shows a confirmation page with the selected name. The action runs
   only when that page is submitted with ``confirmed=1``.

Routes use it like this::

    reviewer, response = require_confirmed_reviewer("hold this draft")
    if response is not None:
        return response          # 400 prompt or the confirmation page; nothing written
    ...write the action, recording ``reviewer``...

Names come only from config.json. No route can add, remove, or edit them.
Selection is honor-system: the app has no sign-in.
"""

from flask import current_app, render_template, request

REVIEWER_FIELD = "reviewer"
CONFIRM_FIELD = "confirmed"


class ReviewerError(Exception):
    """A recorded action without a valid reviewer name. Rendered as HTTP 400."""


def reviewer_names():
    """The authorized names from config.json, read once at app startup (read-only tuple)."""
    return current_app.config["REVIEWERS"]


def selected_reviewer(form):
    """Return the submitted reviewer name, or raise ReviewerError."""
    name = (form.get(REVIEWER_FIELD) or "").strip()
    names = reviewer_names()
    if not names:
        raise ReviewerError(
            "No authorized reviewers are configured, so this action cannot be recorded. "
            "Ask the lab to add the authorized names to config.json."
        )
    if not name:
        raise ReviewerError("Select your name from the reviewer list before continuing.")
    if name not in names:
        raise ReviewerError("That name is not on the authorized reviewer list. Select your name from the list.")
    return name


def require_confirmed_reviewer(action):
    """Return (reviewer, None) when the action may run, else (None, response).

    ``action`` describes the action for the confirmation page, for example
    "hold this draft". The response is the confirmation page (HTTP 200) when
    the name is valid but not yet confirmed. Invalid names raise ReviewerError.
    """
    reviewer = selected_reviewer(request.form)
    if request.form.get(CONFIRM_FIELD) == "1":
        return reviewer, None
    fields = [(key, value) for key, value in request.form.items(multi=True) if key != CONFIRM_FIELD]
    page = render_template("_confirm.html", action=action, reviewer=reviewer, fields=fields,
                           target=request.path)
    return None, page
