"""Compare independent transcriptions and stage growth-log data in SQLite."""

import argparse
import datetime as dt
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path


FIELDS = {
    "name": str,
    "date": str,
    "jc": dict,
    "composition": dict,
    "furnace_cycle": list,
    "technique": str,
    "transport_agent": dict,
    "furnace_layout": dict,
    "timestamps": dict,
    "measurements": list,
}
REQUIRED = {"name", "date", "composition", "furnace_cycle"}
STATUSES = {"recorded", "derived", "inferred", "not_recorded", "illegible", "ambiguous"}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def read_packet(path, *, manifest=False):
    packet = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict) or not isinstance(packet.get("records"), list):
        raise ValueError(f"{path}: expected a JSON object containing a records array")
    records = {}
    for record in packet["records"]:
        if not isinstance(record, dict):
            raise ValueError(f"{path}: each record must be an object")
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip() or record_id in records:
            raise ValueError(f"{path}: blank or duplicate record_id {record_id!r}")
        validate_source(record)
        if not manifest:
            validate_fields(record)
        records[record_id] = record
    return packet.get("extractor"), records


def validate_source(record):
    record_id = record["record_id"]
    source = record.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("file"), str)
        or not source["file"].strip()
        or type(source.get("page")) is not int
        or source["page"] < 1
    ):
        raise ValueError(f"{record_id}: source needs a file and a 1-based page number")


def validate_fields(record):
    record_id = record["record_id"]
    fields = record.get("fields")
    if not isinstance(fields, dict) or fields.keys() != FIELDS.keys():
        raise ValueError(f"{record_id}: expected fields {', '.join(FIELDS)}")

    for name, value_type in FIELDS.items():
        field = fields[name]
        label = f"{record_id}.{name}"
        if not isinstance(field, dict) or not {"status", "value", "evidence"} <= field.keys():
            raise ValueError(f"{label}: expected status, value, and evidence")
        status, value, evidence = (field[key] for key in ("status", "value", "evidence"))
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"{label}: invalid status {status!r}")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError(f"{label}: evidence or a reason for missing data is required")
        if value is not None and (not isinstance(value, value_type) or not value):
            raise ValueError(f"{label}: expected a nonempty {value_type.__name__} or null")
        if status == "not_recorded" and value is not None:
            raise ValueError(f"{label}: not_recorded requires null")
        if status in {"recorded", "derived", "inferred"} and value is None:
            raise ValueError(f"{label}: {status} requires a value")

    date = fields["date"]["value"]
    if date is not None:
        try:
            parsed = dt.date.fromisoformat(f"{date}-01" if len(date) == 7 else date)
            if parsed.isoformat()[:len(date)] != date:
                raise ValueError
        except ValueError:
            raise ValueError(f"{record_id}.date: use a valid YYYY-MM or YYYY-MM-DD") from None

    jc = fields["jc"]["value"]
    if jc is not None:
        raw, full = jc.get("raw"), jc.get("full")
        if not isinstance(raw, str) or not raw.strip() or "full" not in jc:
            raise ValueError(f"{record_id}.jc: preserve raw and include full (or null)")
        if full is not None and (
            not isinstance(full, str) or not full.isascii() or not full.isdecimal()
        ):
            raise ValueError(f"{record_id}.jc: full must be a digit string or null")

    technique = fields["technique"]["value"]
    if technique is not None and technique not in {"flux", "cvt", "other"}:
        raise ValueError(f"{record_id}.technique: use flux, cvt, other, or null")

    layout = fields["furnace_layout"]["value"]
    if layout is not None:
        if type(layout.get("present")) is not bool:
            raise ValueError(f"{record_id}.furnace_layout: present must be a boolean")
        image = layout.get("image")
        if image is not None and (
            not layout["present"] or not isinstance(image, str) or not image.strip()
        ):
            raise ValueError(f"{record_id}.furnace_layout: image must reference a present layout")


def compare(paths, expected_path):
    expected = None
    if expected_path:
        _, expected = read_packet(expected_path, manifest=True)
        if not expected:
            raise ValueError(f"{expected_path}: expected at least one record locator")

    runs = {}
    for path in paths:
        extractor, records = read_packet(path)
        if not isinstance(extractor, str) or not extractor.strip() or extractor in runs:
            raise ValueError(f"{path}: expected a distinct extractor label")
        runs[extractor] = records

    record_ids = set().union(*(records.keys() for records in runs.values()))
    if expected is not None:
        record_ids.update(expected)
    if not record_ids:
        raise ValueError("no records to compare; supply the expected input manifest")

    report = []
    for record_id in sorted(record_ids):
        present = {name: records[record_id] for name, records in runs.items()
                   if record_id in records}
        sources = {name: record["source"] for name, record in present.items()}
        issues = []
        for name in sorted(runs.keys() - present.keys()):
            issues.append({"field": "record", "reason": "missing submission", "extractor": name})
        if len({encode(source) for source in sources.values()}) > 1:
            issues.append({"field": "source", "reason": "page or entry locator disagreement"})
        planned_source = None
        if expected is not None:
            planned = expected.get(record_id)
            if planned is None:
                issues.append({"field": "source", "reason": "record outside input manifest"})
            else:
                planned_source = planned["source"]
                for name, record in present.items():
                    if encode(record["source"]) != encode(planned_source):
                        issues.append({
                            "field": "source", "reason": "locator differs from input manifest",
                            "extractor": name,
                        })

        for field_name in FIELDS:
            values = {name: record["fields"][field_name] for name, record in present.items()}
            candidates = {encode([field["status"], field["value"]]) for field in values.values()}
            reasons = []
            if len(candidates) > 1:
                reasons.append("extractors disagree")
            for name, field in values.items():
                status = field["status"]
                if status in {"derived", "inferred", "illegible", "ambiguous"}:
                    reasons.append(f"{name}: {status}")
                elif status == "not_recorded" and field_name in REQUIRED:
                    reasons.append(f"{name}: required field missing")
                elif field_name == "jc" and field["value"] and field["value"]["full"] is None:
                    reasons.append(f"{name}: full JC number unresolved")
                elif field_name == "furnace_layout" and field["value"]:
                    layout = field["value"]
                    if layout["present"] and not layout.get("image"):
                        reasons.append(f"{name}: layout crop needed")
            if reasons:
                issues.append({"field": field_name, "reasons": reasons, "candidates": values})
        report.append({
            "record_id": record_id,
            "expected_source": planned_source,
            "sources": sources,
            "flag": "red" if issues else "green",
            "issues": issues,
        })
    return {"extractors": list(runs), "records": report}


def import_drafts(path, database):
    _, records = read_packet(path)
    if not records:
        raise ValueError(f"{path}: records array is empty")
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        added = 0
        with connection:
            # Acquire the write lock before checking existing records.
            connection.execute("BEGIN IMMEDIATE")
            for record_id, record in records.items():
                payload = encode(record)
                previous = connection.execute(
                    "SELECT original_json FROM growth_logs WHERE record_id = ?", (record_id,)
                ).fetchone()
                if previous:
                    if previous[0] != payload:
                        raise ValueError(f"{record_id}: already imported; correct working_json instead")
                    continue
                connection.execute(
                    "INSERT INTO growth_logs VALUES (?, ?, ?)", (record_id, payload, payload)
                )
                added += 1
    print(f"Staged {added} of {len(records)} draft records.")


def field(value, evidence, status="recorded"):
    return {"status": status, "value": value, "evidence": evidence}


def adapt_run01(path, source_file):
    """Adapt the saved first pilot result. Keep its raw worksheet JSON separately."""
    worksheet = json.loads(path.read_text(encoding="utf-8"))
    measured = worksheet["measured"]["rows"]
    if any(any(value != "" for value in row.values()) for row in measured):
        raise ValueError("run01 adapter expects an empty Measured table")
    if worksheet["furnace_layout"]["content"] or any(
        worksheet[key] for key in ("start_timestamp", "end_timestamp")
    ):
        raise ValueError("run01 adapter expects a blank layout and blank timestamps")

    raw_date = worksheet["date"]
    date = dt.datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
    calculated = worksheet["calculated"]
    records = []
    for row_number, row in enumerate(calculated["rows"], 1):
        jc = re.fullmatch(r"JC([0-9]+)", row["#"])
        if jc is None:
            raise ValueError(f"Calculated row {row_number}: expected a full JC number")
        compound = row["Compound"]
        x_raw = compound["x"]
        composition = {
            "formula": compound["formula"],
            "x_raw": x_raw,
            "x": x_raw if re.fullmatch(r"(?:0(?:\.[0-9]+)?|1(?:\.0+)?)", x_raw) else None,
            "printed_X": row["X"],
            "charge_ratio_raw": calculated["note"],
            "calculated_quantities_raw": {
                column: row[column] for column in calculated["columns"][3:]
            },
            "margin_annotation_raw": row["right_margin_annotation"],
        }
        fields = {
            "name": field(worksheet["name"], "Worksheet header"),
            "date": field(date, f"Worksheet header reads {raw_date}"),
            "jc": field({"raw": row["#"], "full": jc[1]}, f"Calculated row {row_number}, #"),
            "composition": field(
                composition,
                f"Calculated row {row_number}. Confirm the ratio mapping, reference notes, "
                "margin annotation, and any overwritten x against the page.",
                "ambiguous",
            ),
            "furnace_cycle": field(None, "This legacy JSON has no furnace cycle field.", "ambiguous"),
            "technique": field(None, "Confirm from associated growth records.", "ambiguous"),
            "transport_agent": field(
                None, "This legacy JSON has no transport agent field.", "ambiguous"
            ),
            "furnace_layout": field(
                {"present": False, "image": None}, "The legacy extraction has a blank layout."
            ),
            "timestamps": field(None, "Both timestamp boxes transcribed as blank.", "not_recorded"),
            "measurements": field(None, "Measured rows transcribed as blank.", "not_recorded"),
        }
        records.append({
            "record_id": f"worksheet-01-p1-calculated-{row_number}",
            "source": {"file": source_file, "page": 1, "section": "Calculated", "row": row_number},
            "fields": fields,
        })
    return {"extractor": "chatgpt_pdf-to-json_run01", "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    comparison = commands.add_parser("compare", help="report field-level disagreements as JSON")
    comparison.add_argument("packets", type=Path, nargs="+")
    comparison.add_argument("--expected", type=Path, help="manifest of expected record locators")
    importer = commands.add_parser("import", help="stage a JSON packet in the local sandbox")
    importer.add_argument("packet", type=Path)
    importer.add_argument("database", type=Path)
    adapter = commands.add_parser("adapt-run01", help="map the saved legacy pilot JSON to a packet")
    adapter.add_argument("legacy_json", type=Path)
    adapter.add_argument("source_file", help="original PDF locator, relative to the repo or a Drive URL")
    args = parser.parse_args()
    try:
        if args.command == "compare":
            if len(args.packets) < 2:
                raise ValueError("comparison needs at least two independent packets")
            print(json.dumps(compare(args.packets, args.expected), ensure_ascii=False,
                             indent=2, allow_nan=False))
        elif args.command == "import":
            import_drafts(args.packet, args.database)
        else:
            print(json.dumps(adapt_run01(args.legacy_json, args.source_file),
                             ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
