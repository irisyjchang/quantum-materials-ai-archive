"""Tests for restore verification and the backup line on the status view (Tasks 23.4, 23.6; Requirements 26.3, 26.7).

Temporary databases and folders only.
"""

from datetime import datetime, timedelta

import pytest

from common import backup_status
from conftest import query
from review_app.app import create_app
from review_helpers import make_review
from tools import backup, restore, verify_restore


@pytest.fixture
def restored(workspace, tmp_path_factory):
    """A restored Test folder holding one approved and revised run, one pending draft, and its retained PDF."""
    review = make_review(workspace)
    assert review.approve("draft-r1").status_code == 302
    run_id = query(review.database, "SELECT run_id FROM growth_runs")[0][0]
    page = review.client.get(f"/runs/{run_id}").get_data(as_text=True)
    version = page.split('name="opened_version" value="')[1].split('"')[0]
    response = review.client.post(f"/runs/{run_id}/revise", data={
        "field": "jc_number", "new_value": "0697", "reason": "JC cell reads 0697", "reviewer": "Reviewer A",
        "opened_version": version, "confirmed": "1",
        "verified_location": "yes", "verified_lookup": "yes", "verified_stoichiometry": "yes"})
    assert response.status_code == 302
    assert query(review.database, "SELECT count(*) FROM run_revisions") == [(2,)]
    dest = tmp_path_factory.mktemp("backups")
    assert backup.main(["snapshot", "--env", "test", "--dest", str(dest), "--root", str(workspace.root)]) == 0
    target = tmp_path_factory.mktemp("drill") / "restored"
    restore.restore(next(dest.iterdir()), target)
    return target


def by_name(verification):
    return {check.name: check for check in verification.checks}


def test_complete_restore_passes(restored, capsys):
    verification = verify_restore.verify(restored)
    assert verification.ok, verify_restore.render(verification)
    assert verify_restore.main([str(restored)]) == 0
    output = capsys.readouterr().out
    for line in ("PASS  Approved runs are searchable", "PASS  Review history is present",
                 "PASS  Source PDF links open the exact versions", "Elapsed restore time:",
                 "Newest restored approval:", "pending lab confirmation", "Restore check passed."):
        assert line in output
    assert "2 revisions for 1 approved runs" in output


def test_newest_approval_age_is_reported(restored):
    newest = query(restored / "test.sqlite", "SELECT max(approved_at) FROM run_revisions")[0][0]
    later = datetime.fromisoformat(newest) + timedelta(hours=30)
    verification = verify_restore.verify(restored, now=later)
    assert verification.newest_approval_at == newest
    assert verification.newest_approval_age_seconds == pytest.approx(30 * 3600)
    assert "30 h 0 min 0 s" in verify_restore.render(verification)


def test_missing_pdf_fails(restored, capsys):
    path = query(restored / "test.sqlite", "SELECT storage_path FROM source_pdfs")[0][0]
    (restored / "retained_pdfs" / "test" / path.rsplit("/", 1)[1]).unlink()
    check = by_name(verify_restore.verify(restored))["Source PDF links open the exact versions"]
    assert not check.ok and "retained copy is missing" in check.details[0]
    assert verify_restore.main([str(restored)]) == 1
    assert "Restore check FAILED." in capsys.readouterr().out


def test_hash_mismatch_fails(restored):
    path = query(restored / "test.sqlite", "SELECT storage_path FROM source_pdfs")[0][0]
    with open(path, "ab") as handle:
        handle.write(b"% changed\n")
    check = by_name(verify_restore.verify(restored))["Source PDF links open the exact versions"]
    assert not check.ok and "does not equal file_hash" in check.details[0]


def test_storage_path_outside_the_restored_folder_fails(restored, workspace):
    live = query(workspace.root / "test.sqlite", "SELECT storage_path FROM source_pdfs")[0][0]
    query(restored / "test.sqlite", "UPDATE source_pdfs SET storage_path = ?", (live,))
    check = by_name(verify_restore.verify(restored))["Source PDF links open the exact versions"]
    assert not check.ok and "outside the restored folder" in check.details[0]


def test_missing_revision_history_fails(restored):
    query(restored / "test.sqlite", "PRAGMA foreign_keys = OFF")
    query(restored / "test.sqlite", "DELETE FROM run_revisions WHERE version = 1")
    check = by_name(verify_restore.verify(restored))["Review history is present"]
    assert not check.ok and "versions are not 1 to 1" in check.details[0]


def test_missing_table_fails(restored):
    query(restored / "test.sqlite", "DROP TABLE growth_runs")
    verification = verify_restore.verify(restored)
    assert not verification.ok
    assert "missing tables: growth_runs" in by_name(verification)["Database opens and has the MVP schema"].details


def test_no_approved_runs_fails(workspace, tmp_path_factory):
    make_review(workspace)
    dest = tmp_path_factory.mktemp("backups")
    assert backup.main(["snapshot", "--env", "test", "--dest", str(dest), "--root", str(workspace.root)]) == 0
    target = tmp_path_factory.mktemp("drill") / "restored"
    restore.restore(next(dest.iterdir()), target)
    check = by_name(verify_restore.verify(target))["Approved runs are searchable"]
    assert not check.ok and "no approved runs" in check.details[0]


def test_missing_database_or_report_fails(tmp_path, restored):
    assert not verify_restore.verify(tmp_path / "nothing-here").ok
    (restored / "restore_report.json").unlink()
    verification = verify_restore.verify(restored)
    assert not by_name(verification)["Restore report is present"].ok


# Status view (23.4) ----------------------------------------------------------------------------------

def status_page(workspace):
    workspace.database("test")
    return create_app("test", root=workspace.root).test_client().get("/status").get_data(as_text=True)


def test_status_view_without_any_backup(workspace):
    assert "No successful backup recorded for this environment." in status_page(workspace)


def test_status_view_shows_last_success_and_later_failure(workspace):
    backup_status.record_success(workspace.root, "test", {
        "at": "2026-11-16T10:00:00.000000+00:00", "snapshot": "/backups/growth-log-test-1", "reason": "daily"})
    page = status_page(workspace)
    assert "Last successful backup: 2026-11-16T10:00:00.000000+00:00" in page and "(daily)" in page
    assert "backup-failure" not in page

    backup_status.record_failure(workspace.root, "test", {
        "at": "2026-11-17T10:00:00.000000+00:00", "error": "backup folder not found: /gone"})
    page = status_page(workspace)
    assert "Last successful backup: 2026-11-16T10:00:00.000000+00:00" in page
    assert "Last backup attempt failed at 2026-11-17T10:00:00.000000+00:00" in page
    assert "backup folder not found: /gone." in page


def test_status_view_hides_a_failure_older_than_the_last_success(workspace):
    backup_status.record_failure(workspace.root, "test", {"at": "2026-11-15T10:00:00+00:00", "error": "x"})
    backup_status.record_success(workspace.root, "test", {"at": "2026-11-16T10:00:00+00:00", "snapshot": "s"})
    assert "Last backup attempt failed" not in status_page(workspace)


def test_status_view_reports_an_unreadable_status_file(workspace):
    path = backup_status.status_path(workspace.root, "test")
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert "cannot be read" in status_page(workspace)


def test_archive_status_is_separate_from_test(workspace):
    backup_status.record_success(workspace.root, "archive", {"at": "2026-11-16T10:00:00+00:00", "snapshot": "a"})
    assert "No successful backup recorded" in status_page(workspace)
