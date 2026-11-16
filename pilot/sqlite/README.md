# Growth logs in SQLite

Allow 10–20 minutes. Run the commands from the archive repository root with Python 3 and `sqlite3` available. The examples use the built-in Python on this Mac, `/usr/bin/python3`. The walkthrough uses the first pilot extraction to make a local staging database. A SQLite database is a single binary file you query with SQL. The original worksheet and raw extraction stay in the run folder.

## 1. Import the three draft rows

```sh
pilot_dir=$(mktemp -d)
run=pilot/runs/chatgpt/pdf-to-json/run01
/usr/bin/python3 pilot/sqlite/pilot.py adapt-run01 "$run/output.json" "$run/1.pdf" > "$pilot_dir/run01.json"
/usr/bin/python3 pilot/sqlite/pilot.py import "$pilot_dir/run01.json" "$pilot_dir/growth-logs.sqlite"
sqlite3 "$pilot_dir/growth-logs.sqlite"
```

The adapter is specific to the saved Run 01 format. It maps the three populated Calculated rows to stable source positions and keeps the original strings for composition and quantities. The database is for staging and practice. All three entries are unvalidated.

## 2. Search and sort

In the SQLite prompt, try these queries. The source file and page identify where to verify the result.

```sql
.headers on
.mode column

SELECT jc_written, name, growth_date, source_page, layout_present
FROM growth_log_index
ORDER BY growth_date IS NULL, growth_date, jc_number IS NULL,
         CAST(jc_number AS INTEGER), name COLLATE NOCASE, record_id;

SELECT jc_written, growth_date, source_file, source_page
FROM growth_log_index
WHERE jc_number = '1302' OR jc_written = 'JC1302';

SELECT jc_written, name, growth_date
FROM growth_log_index
WHERE name LIKE '%Yue%' AND growth_date LIKE '2020-01%';
```

Expect three January 16 rows, with JC1302 alone in the second query. A date with month precision sorts before dated entries in that month and displays without a day. The month search includes both kinds of dates. For records without a confirmed JC that share a date, the first query sorts by name.

## 3. Inspect and practice a correction

```sql
SELECT json_extract(working_json, '$.fields.composition.value.x_raw') AS x_as_read,
       json_extract(working_json, '$.fields.composition.value.x') AS x_normalized,
       json_extract(working_json, '$.fields.composition.evidence') AS review_note
FROM growth_logs
WHERE record_id = 'worksheet-01-p1-calculated-2';

BEGIN;
UPDATE growth_logs
SET working_json = json_set(working_json, '$.fields.name.value', 'Practice edit')
WHERE record_id = 'worksheet-01-p1-calculated-2';

SELECT json_extract(original_json, '$.fields.name.value') AS original_name,
       json_extract(working_json, '$.fields.name.value') AS edited_name
FROM growth_logs
WHERE record_id = 'worksheet-01-p1-calculated-2';

ROLLBACK;
SELECT name FROM growth_log_index WHERE jc_number = '1302';
.quit
```

The working copy changes while the original import is still available. The rollback restores the working copy to Yue. For an actual correction, record the reviewer, date, and reason along with the page evidence. The walkthrough stages data and demonstrates corrections. The shared app's approval workflow and review history belong to the [MVP design](../../DESIGN-MVP.md).

Reimporting the same packet stages zero additional rows and keeps the working copy. Reusing an ID with different imported content reports a conflict and rolls back the batch.

## Comparison packet

Use `adapt-run01` to see a complete packet shape. Each new run should have an `extractor` label, a `records` array, and the same preassigned `record_id` and source locator for each row. Each record needs `name`, `date`, `jc`, `composition`, `furnace_cycle`, `technique`, `transport_agent`, `furnace_layout`, `timestamps`, and `measurements` in `fields`.

Each field holds `value`, `status`, and `evidence`. Use `recorded` for a direct transcription or formatting normalization, `derived` for a calculation, `inferred` for a contextual interpretation, `not_recorded` with a null value for an inspected blank or absent entry, `illegible` for unreadable writing, and `ambiguous` for multiple possible readings. Evidence should give the region and original text or explain why a value is missing. Keep partial values and readable text where possible. For dates, use ISO day or month precision. For JC use `{"raw":"JC1302","full":"1302"}`, with `full: null` when only a suffix is known.

Keep subfield names and representations identical across runs. For the furnace cycle, use an ordered array with one object per step. Use `kind` (`ramp`, `dwell`, `decant`, or `other`), `start_temp`, `target_temp`, `temperature_unit`, `duration_hours`, and `rate` where applicable. Put simultaneously labeled temperatures in `zone_temperatures` under the original labels. Keep the original wording or graph location in evidence and use null for an unspecified parameter. For layout use `{"present":false,"image":null}` when absent, and `present: true` with the shared crop path when a drawing exists. Use an ambiguous null value if the page is insufficient to tell.

Before running the models, save the input manifest as `expected.json`. Give it a `records` array with only the preassigned `record_id` and `source` for each expected record. Use the manifest in the comparison so it can flag rows omitted by every extractor. Run the comparison from the repository root with paths to the manifest and the five independently saved packets.

```sh
/usr/bin/python3 pilot/sqlite/pilot.py compare --expected expected.json \
  chatgpt.json claude.json muse.json gemini.json grok.json > comparison.json
```

The report shows submitted extractors, source locators, red or green flags, and competing readings for each flagged field. Object key order is ignored. List order, statuses, units, raw strings, and numeric representations are compared as supplied. Evidence wording is retained for review and does not count as disagreement by itself. The report is a comparison for the supplied runs and does not approve records or verify against the scan. The guide describes the human check before archive import. [Field guide and pilot plan](../field-guide.md)
