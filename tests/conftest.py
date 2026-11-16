"""Shared fixtures: an isolated workspace with its own config, databases, and a fixture PDF."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from common.config import CONFIG_ENV_VARIABLE
from db.init_db import initialize
from factories import extraction_packet, risk_packet
import staging

PDF_BYTES = b"%PDF-1.4\n% placeholder fixture, not a lab scan\n"


@dataclass
class Workspace:
    root: Path
    config_path: Path
    checklist_path: Path
    pdf: Path
    pdf_hash: str

    def database(self, name="test"):
        path = self.root / f"{name}.sqlite"
        if not path.exists():
            initialize(path)
        return path

    def write_packet(self, packet, name="packet.json"):
        path = self.root / name
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def make_pdf(self, name, content):
        path = self.root / "scans" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path, hashlib.sha256(content).hexdigest()

    def reserve(self, *drive_file_ids):
        entries = [{"drive_file_id": item} for item in drive_file_ids]
        self.checklist_path.write_text(json.dumps({"walkthrough": [], "acceptance": entries}), encoding="utf-8")

    def risk_assess(self, packet, database=None, source_pdf=None, acceptance_run=False):
        """Run risk-assess in-process and return the exit code."""
        packet_path = self.write_packet(packet)
        argv = ["risk-assess", str(packet_path), "--source-pdf", str(source_pdf or self.pdf)]
        if acceptance_run:
            argv.append("--acceptance-run")
        argv.append(str(database or self.database()))
        return staging.main(argv)

    def risk_packet(self, decision="non_critical", issues=None, **overrides):
        overrides.setdefault("file_hash", self.pdf_hash)
        return risk_packet(decision, issues, **overrides)

    def extraction_packet(self, runs=None, **overrides):
        overrides.setdefault("file_hash", self.pdf_hash)
        return extraction_packet(runs, **overrides)

    def stage_drafts(self, packet, database=None, acceptance_run=False):
        """Run stage-drafts in-process and return the exit code."""
        packet_path = self.write_packet(packet, "extraction.json")
        argv = ["stage-drafts", str(packet_path)]
        if acceptance_run:
            argv.append("--acceptance-run")
        argv.append(str(database or self.database()))
        return staging.main(argv)


def query(database, sql, params=()):
    """Run one statement against a test database, committing any change it makes."""
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(sql, params).fetchall()
        connection.commit()
        return rows
    finally:
        connection.close()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    checklist = tmp_path / "test_checklist.json"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "reviewers": ["Reviewer A"],
        "backup_folder": None,
        "backup_name_pattern": None,
        "checklist_path": str(checklist),
        "filename_index_path": str(tmp_path / "filename_index.json"),
    }), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV_VARIABLE, str(config))
    pdf = tmp_path / "scans" / "log-1-901.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(PDF_BYTES)
    return Workspace(tmp_path, config, checklist, pdf, hashlib.sha256(PDF_BYTES).hexdigest())
