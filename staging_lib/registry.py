"""source_pdfs registration (Task 4.3, Requirements 1.4, 1.5, 1.6, 8.5).

A version is identified by drive_file_id + file_hash. The internal pdf_id is
derived from that pair, so registering the same version twice gives the same ID.
"""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePdf:
    pdf_id: str
    archive_filename: str
    drive_file_id: str
    file_hash: str
    storage_path: object


def pdf_id_for(drive_file_id, file_hash):
    digest = hashlib.sha256(f"{drive_file_id}\n{file_hash}".encode("utf-8")).hexdigest()
    return f"pdf-{digest[:20]}"


def find_version(connection, drive_file_id, file_hash):
    """Return the registered SourcePdf for this version, or None."""
    row = connection.execute(
        "SELECT pdf_id, archive_filename, drive_file_id, file_hash, storage_path"
        " FROM source_pdfs WHERE drive_file_id = ? AND file_hash = ?",
        (drive_file_id, file_hash),
    ).fetchone()
    return SourcePdf(*row) if row else None


def register(connection, drive_file_id, file_hash, archive_filename, storage_path):
    """Insert a new version and return it. The caller checks it is not already registered."""
    source = SourcePdf(pdf_id_for(drive_file_id, file_hash), archive_filename,
                       drive_file_id, file_hash, str(storage_path))
    connection.execute(
        "INSERT INTO source_pdfs (pdf_id, archive_filename, drive_file_id, file_hash, storage_path)"
        " VALUES (?, ?, ?, ?, ?)",
        (source.pdf_id, source.archive_filename, source.drive_file_id, source.file_hash,
         source.storage_path),
    )
    return source


def set_storage_path(connection, pdf_id, storage_path):
    """Fill a missing storage_path on a registered version (never replaces an existing value)."""
    connection.execute(
        "UPDATE source_pdfs SET storage_path = ? WHERE pdf_id = ? AND storage_path IS NULL",
        (str(storage_path), pdf_id),
    )
