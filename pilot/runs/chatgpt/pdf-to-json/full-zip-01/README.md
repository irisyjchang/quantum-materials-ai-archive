# Full ZIP transcription — organized by source, page, and sample

**[Browse individual pages and sample identifiers](page-index.md)** · **[Download/view the complete organized JSON](output.json)**

The source is `quantum_materials_lab.zip`: 36 pages from `GrowthLogScan.pdf`, 22 pages from `10202026GrowthLogScan2.pdf`, and four bottle-label photos inside `attachments.zip`. The source PDFs are not included in this folder. `source_page` is the one-based PDF page number, so each entry can be located in the original ZIP.

## Finding a sample

Open the page index and find an identifier, such as JC1301. Open that page's JSON. Each object in `samples` begins a separate sample group, with `identifier_as_written` at its start and its explicitly identified `Calculated` and `Measured` rows underneath. Some identifiers are just numbers or local labels; these are kept exactly as transcribed, without assuming a JC prefix.

Measured rows with no identifier remain in `unassigned_rows.Measured`. Where available, `same_position_calculated_identifier` points to the calculated row at the same position; this is a navigation hint, **not a verified match**. Blank rows remain in `blank_rows`, with their original row numbers. `table_columns` preserves the original column order, including duplicate or empty headers. Page-level notes, furnace layout, load, and timestamps remain attached to their page.

This is **not sorted by date**. Dates remain in `top_annotations` exactly as transcribed, because unclear or overwritten dates should not determine ordering.

## Validation status

**Unvalidated transcription.** This change only reorganizes the previous full-ZIP output; it does not correct or verify handwriting, chemical formulas, quantities, sample identifiers, or label grids. It does not establish extraction accuracy or resume performance metrics. The earlier single-worksheet `run01` remains separate and unchanged.

- [Original full-ZIP output](original-output.json) is preserved unchanged.
- [Complete organized JSON](output.json) contains all six source PDFs and all 62 pages/images.
- `sources/` provides smaller files for browsing individual pages and photos on GitHub.
- [Reorganization script](organize.py) rebuilds the organized files and asserts that every original table row, including blanks, is preserved exactly once with all cell values unchanged.

Run `python3 organize.py` from this folder to regenerate and verify the files. JSON syntax and structural preservation are checked; scientific and transcription accuracy still require comparison with the scans.
