"""Tests for the shared connection helper (Task 2.7)."""

import sqlite3

import pytest

from db.connect import BUSY_TIMEOUT_MS, connect
from db.init_db import initialize


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "test.sqlite"
    initialize(path)
    return path


def test_new_connection_has_mvp_settings(database):
    connection = connect(database)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
    finally:
        connection.close()


def test_foreign_keys_are_enforced(database):
    connection = connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO draft_runs (draft_id, pdf_id, source_locations_json, original_json,"
                " review_status) VALUES ('d', 'no-such-pdf', '[]', '{}', 'Pending review')"
            )
    finally:
        connection.close()


def test_readers_continue_while_a_writer_holds_a_transaction(database):
    writer = connect(database)
    reader_one = connect(database)
    reader_two = connect(database, read_only=True)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash)"
            " VALUES ('p', 'log-1-901.pdf', 'd', 'h')"
        )
        # Both readers see the last committed state without waiting for the writer.
        assert reader_one.execute("SELECT count(*) FROM source_pdfs").fetchone()[0] == 0
        assert reader_two.execute("SELECT count(*) FROM source_pdfs").fetchone()[0] == 0
        writer.commit()
        assert reader_one.execute("SELECT count(*) FROM source_pdfs").fetchone()[0] == 1
    finally:
        for connection in (writer, reader_one, reader_two):
            connection.close()


def test_read_only_connection_cannot_write(database):
    connection = connect(database, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash)"
                " VALUES ('p', 'f', 'd', 'h')"
            )
    finally:
        connection.close()
