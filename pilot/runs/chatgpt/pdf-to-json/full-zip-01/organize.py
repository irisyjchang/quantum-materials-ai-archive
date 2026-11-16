"""Reorganize the existing transcription without changing its cell values."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def identifier(row):
    return row.get("#", row.get("JC#", "")).strip()


def occupied(value):
    if isinstance(value, dict):
        return any(occupied(v) for k, v in value.items() if k != "column")
    if isinstance(value, list):
        return any(occupied(v) for v in value)
    return value != ""


def organize_page(raw, source, number):
    page = {
        "source_file": source,
        "source_page": number,
        "review_status": "unvalidated",
        "top_annotations": raw["top annotations"],
        "table_columns": {
            "Calculated": raw["Calculated"]["columns"],
            "Measured": raw["Measured"]["columns"],
        },
        "samples": [],
        "unassigned_rows": {"Calculated": [], "Measured": []},
        "blank_rows": {"Calculated": [], "Measured": []},
    }
    sample_map = {}
    for section in ("Calculated", "Measured"):
        for index, row in enumerate(raw[section]["rows"], 1):
            record = {"row_number": index, "transcription": copy.deepcopy(row)}
            if not occupied(row):
                page["blank_rows"][section].append(record)
                continue
            sample_id = identifier(row)
            if sample_id and "[" not in sample_id:
                if sample_id not in sample_map:
                    sample_map[sample_id] = {
                        "identifier_as_written": sample_id,
                        "Calculated": [],
                        "Measured": [],
                    }
                    page["samples"].append(sample_map[sample_id])
                sample_map[sample_id][section].append(record)
            else:
                if section == "Measured" and index <= len(raw["Calculated"]["rows"]):
                    candidate = identifier(raw["Calculated"]["rows"][index - 1])
                    if candidate:
                        record["same_position_calculated_identifier"] = candidate
                        record["match_status"] = "unassigned; row position only"
                page["unassigned_rows"][section].append(record)
    for key, value in raw.items():
        if key not in ("top annotations", "Calculated", "Measured"):
            page[key] = copy.deepcopy(value)
    # Verify every original row, including blank and ambiguous rows, survives.
    for section in ("Calculated", "Measured"):
        records = page["unassigned_rows"][section] + page["blank_rows"][section]
        records += [r for s in page["samples"] for r in s[section]]
        records.sort(key=lambda r: r["row_number"])
        assert [r["row_number"] for r in records] == list(range(1, len(raw[section]["rows"]) + 1))
        assert [r["transcription"] for r in records] == raw[section]["rows"]
    return page


def main():
    original = json.loads((ROOT / "original-output.json").read_text())
    assert len(original["papers"]) == 58
    assert len(original["labels"]) == 4
    output = {
        "review_status": "unvalidated",
        "organization": "source file, original page order, identifier as written",
        "matching_rule": "Only identical explicit identifiers are grouped; unlabeled or uncertain rows remain unassigned.",
        "sources": [],
    }
    index_lines = []
    offset = 0
    for filename, count in (("GrowthLogScan.pdf", 36), ("10202026GrowthLogScan2.pdf", 22)):
        source = {"source_file": filename, "pages": []}
        index_lines += [f"\n### {filename}\n"]
        for number in range(1, count + 1):
            page = organize_page(original["papers"][offset], filename, number)
            offset += 1
            source["pages"].append(page)
            relative = f"sources/{Path(filename).stem}/page-{number:03}.json"
            write(ROOT / relative, page)
            ids = ", ".join(s["identifier_as_written"] for s in page["samples"])
            index_lines.append(f"- [Page {number}]({relative}) — {ids or 'no unambiguous identifier transcribed'}")
        output["sources"].append(source)
    for filename, grid in zip(("JC300s.pdf", "JC400ss.pdf", "JC500s.pdf", "JC600s.pdf"), original["labels"]):
        source = {"source_file": f"attachments.zip/{filename}", "pages": [{"source_page": 1, "labels": grid}]}
        output["sources"].append(source)
        relative = f"sources/attachments/{Path(filename).stem}.json"
        write(ROOT / relative, source)
        index_lines.append(f"- [{filename}]({relative}) — bottle-label grid")
    write(ROOT / "output.json", output)
    (ROOT / "page-index.md").write_text("# Page index\n\nEach link opens one source page. Identifiers below are copied from the unvalidated transcription; they are not corrected or normalized.\n" + "\n".join(index_lines) + "\n")
    print("Validated: 58 pages, 4 label grids; every original table row preserved exactly.")


if __name__ == "__main__":
    main()
