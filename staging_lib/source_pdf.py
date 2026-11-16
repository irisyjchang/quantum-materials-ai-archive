"""Source PDF hash verification (Task 3.4, Requirements 8.5, 21.6)."""

import hashlib
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


def sha256_file(path):
    """Return the SHA-256 hex digest of the file, streamed in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_hash(path, expected_hash):
    """Return None when the file's SHA-256 equals ``expected_hash``, else an error string."""
    path = Path(path)
    if not path.is_file():
        return f"source PDF not found or not a file: {path}"
    try:
        actual = sha256_file(path)
    except OSError as error:
        return f"source PDF could not be read: {path}: {error}"
    if actual != str(expected_hash).strip().lower():
        return f"the file bytes at {path} do not match file_hash (SHA-256 is {actual})"
    return None
