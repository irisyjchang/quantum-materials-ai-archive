"""Helpers for review-flow tests: stage drafts in a temporary Test database and drive the app.

The reviewer name "Reviewer A" comes from the temporary test config in conftest.py.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from conftest import query
from factories import run
from review_app.app import create_app

REVIEWER = "Reviewer A"
VERIFIED = {"verified_location": "yes", "verified_lookup": "yes", "verified_stoichiometry": "yes"}


@dataclass
class Review:
    workspace: object
    database: Path
    client: object
    pdf_id: str
    storage_path: Path

    def draft(self, draft_id):
        return query(self.database, "SELECT review_status, hold_reason, updated_at, original_json"
                                    " FROM draft_runs WHERE draft_id = ?", (draft_id,))[0]

    def counts(self):
        return {table: query(self.database, f"SELECT count(*) FROM {table}")[0][0]
                for table in ("growth_runs", "run_revisions")}

    def corrections_file(self, draft_id):
        return self.workspace.root / "review_workspace" / "test" / "corrections" / f"{draft_id}.json"

    def corrections(self, draft_id):
        path = self.corrections_file(draft_id)
        return json.loads(path.read_text(encoding="utf-8"))["corrections"] if path.exists() else []

    def actions(self):
        path = self.workspace.root / "review_workspace" / "test" / "actions.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def digest(self):
        return hashlib.sha256(self.database.read_bytes()).hexdigest()

    # Actions, always confirmed as REVIEWER unless overridden.
    def correct(self, draft_id, field, new_value, reason="matches the source PDF", confirmed=True, **extra):
        data = {"field": field, "new_value": new_value, "reason": reason, "reviewer": REVIEWER, **extra}
        if confirmed:
            data["confirmed"] = "1"
        return self.client.post(f"/drafts/{draft_id}/correct", data=data)

    def hold(self, draft_id, reason="unit unclear", confirmed=True, **extra):
        data = {"hold_reason": reason, "reviewer": REVIEWER, **extra}
        if confirmed:
            data["confirmed"] = "1"
        return self.client.post(f"/drafts/{draft_id}/hold", data=data)

    def opened_state(self, draft_id):
        """The hidden state fields from the approval page, as the reviewer's browser would carry them."""
        page = self.client.get(f"/drafts/{draft_id}/approve").get_data(as_text=True)
        return {name: (re.search(rf'name="{name}" value="([^"]*)"', page) or [None, ""])[1]
                for name in ("opened_updated_at", "opened_version")}

    def approve(self, draft_id, state=None, confirmed=True, verified=True, **extra):
        data = dict(state if state is not None else self.opened_state(draft_id))
        data["reviewer"] = REVIEWER
        if verified:
            data.update(VERIFIED)
        if confirmed:
            data["confirmed"] = "1"
        data.update(extra)
        return self.client.post(f"/drafts/{draft_id}/approve", data=data)


def make_review(workspace, runs=None):
    database = workspace.database("test")
    assert workspace.risk_assess(workspace.risk_packet(), database=database) == 0
    runs = runs if runs is not None else [run("draft-r1", row=1), run("draft-r2", row=2)]
    assert workspace.stage_drafts(workspace.extraction_packet(runs), database=database) == 0
    pdf_id, storage_path = query(database, "SELECT pdf_id, storage_path FROM source_pdfs")[0]
    client = create_app("test", root=workspace.root).test_client()
    return Review(workspace, database, client, pdf_id, Path(storage_path))
