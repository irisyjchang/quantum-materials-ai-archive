"""Envelope validation shared by risk and extraction packets (Task 3.1, Requirements 21.1, 21.2)."""

SUPPORTED_SCHEMA_VERSIONS = (1,)
STAGES = ("risk", "extraction")
REQUIRED_STRING_KEYS = ("stage", "drive_file_id", "file_hash", "model", "prompt_version")


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_envelope(packet):
    """Return a descriptive error string, or None when the envelope is valid."""
    if not isinstance(packet, dict):
        return "packet must be a JSON object"
    if "schema_version" not in packet:
        return "packet is missing schema_version"
    version = packet["schema_version"]
    if not _is_integer(version) or version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)
        return f"unsupported schema_version {version!r}; supported: {supported}"
    for key in REQUIRED_STRING_KEYS:
        value = packet.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"packet is missing {key} or it is empty"
    if packet["stage"] not in STAGES:
        return f"unknown stage {packet['stage']!r}; use risk or extraction"
    return None
