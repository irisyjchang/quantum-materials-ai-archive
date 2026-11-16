"""Retained copies of source PDFs (Task 4.2, Requirements 1.9, 8.5).

A retained copy keeps the exact bytes that were assessed, so a reviewer can
open the same version later even if the Drive file is replaced. A copy is
written through a temporary file and never overwrites an existing file.
"""

import os
import re
import shutil
from pathlib import Path

from staging_lib.source_pdf import sha256_file

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class RetainError(OSError):
    pass


def retained_name(drive_file_id, file_hash):
    """File name for a version: <drive_file_id>-<file_hash>.pdf, with unsafe characters replaced."""
    return f"{_UNSAFE.sub('_', drive_file_id)}-{file_hash}.pdf"


def copy_verified(source, destination, file_hash):
    """Copy ``source`` to ``destination`` unless ``destination`` already exists.

    Returns True when this call created the file. The copy is checked against
    ``file_hash`` after writing; a mismatch removes it and raises RetainError.
    """
    destination = Path(destination)
    if destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != file_hash:
            raise RetainError(f"retained copy of {source} does not match file_hash after copying")
        try:
            os.link(temporary, destination)  # fails if destination appeared meanwhile; never overwrites
        except FileExistsError:
            return False
        except OSError:
            if destination.exists():
                return False
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def remove_created(path):
    """Remove a retained copy that this command created, after a failed transaction."""
    if path is not None and Path(path).exists():
        Path(path).unlink()
