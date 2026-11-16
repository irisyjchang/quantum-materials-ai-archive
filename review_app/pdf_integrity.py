"""Retained-copy integrity check (Task 13.3, Requirements 8.3, 8.6).

When a source PDF is opened, the SHA-256 of its retained copy is compared
with file_hash. A missing or changed copy is reported in the viewer panel and
blocks approval of that PDF's drafts until the copy is restored (for example
by rerunning risk-assess with --source-pdf, which recreates a missing copy).
"""

from dataclasses import dataclass
from pathlib import Path

from staging_lib.source_pdf import sha256_file

OK, MISSING, MISMATCH = "ok", "missing", "mismatch"


@dataclass(frozen=True)
class Integrity:
    state: str
    message: str

    @property
    def ok(self):
        return self.state == OK

    @property
    def blocks_approval(self):
        return self.state != OK


def check_retained_copy(storage_path, file_hash):
    """Return the Integrity of the retained copy for one source PDF version."""
    if not storage_path:
        return Integrity(MISSING, "No retained copy is recorded for this PDF version.")
    path = Path(storage_path)
    if not path.is_file():
        return Integrity(MISSING, f"The retained copy is missing: {path}. Rerun risk-assess with --source-pdf "
                                  "to restore it.")
    try:
        actual = sha256_file(path)
    except OSError as error:
        return Integrity(MISSING, f"The retained copy could not be read: {path}: {error}")
    if actual != (file_hash or "").lower():
        return Integrity(MISMATCH, "The retained copy no longer matches the assessed version (its SHA-256 "
                                   "differs from file_hash). It is not shown, and approval of this PDF's "
                                   "drafts is blocked until the original copy is restored.")
    return Integrity(OK, "Retained copy matches the assessed version.")
