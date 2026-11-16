"""Packet loading and validation (Task 3.5, Requirements 21.1, 21.2, 21.6, 24.2).

Validation never opens the database, so a rejected packet leaves it unchanged.
Commands catch PacketError, print its message, and exit with code 1.
"""

import json
from pathlib import Path

from staging_lib.validate_envelope import validate_envelope
from staging_lib.validate_extraction import validate_extraction
from staging_lib.validate_risk import validate_risk

STAGE_VALIDATORS = {"risk": validate_risk, "extraction": validate_extraction}


class PacketError(ValueError):
    """A packet that must not be staged. The message is shown to the operator."""


def validate_packet(packet, expected_stage):
    """Return a descriptive error string, or None when the packet is valid for the stage."""
    error = validate_envelope(packet)
    if error:
        return error
    if packet["stage"] != expected_stage:
        return f"expected a {expected_stage} packet but stage is {packet['stage']!r}"
    return STAGE_VALIDATORS[expected_stage](packet)


def load_packet(path, expected_stage):
    """Read and validate a JSON packet. Raises PacketError on any problem."""
    if expected_stage not in STAGE_VALIDATORS:
        raise ValueError(f"unknown stage {expected_stage!r}")
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PacketError(f"packet not found: {path}") from None
    except (OSError, UnicodeDecodeError) as error:
        raise PacketError(f"packet could not be read: {path}: {error}") from None
    try:
        packet = json.loads(text)
    except json.JSONDecodeError as error:
        raise PacketError(f"packet is not valid JSON: {path}: {error}") from None
    error = validate_packet(packet, expected_stage)
    if error:
        raise PacketError(f"{path}: {error}")
    return packet
