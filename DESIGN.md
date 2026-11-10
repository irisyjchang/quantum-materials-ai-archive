# Quantum Materials Lab — Growth Log Archive Design

**Draft for lab review** · Version 0.5 · November 8, 2026

**Scope** · Automated processing of existing Drive logs, followed by a pilot with in-app photo uploads

## 1. Problem and outcome

A researcher looking for a past log run may have to open several handwritten growth logs and cross-reference a JC number, date, compound, or furnace cycle. A log run is one crystal growth experiment documented in a paper log. One log can contain several log runs. JC numbers were introduced later, so some older log runs lack one. Some numbers are partial or appear on more than one run.

1. **Skill walkthrough.** Run the Codex skill on a few source logs and verify that eligible runs appear in the review app as Pending review. Approve a run and find it in archive search.
2. **Local MVP.** Run the app on the project operator’s laptop. One lab-authorized reviewer checks and approves runs on that laptop. The operator can serve as reviewer if the lab authorizes them. The app can search approved runs and open the source log at the relevant row in the measurement table.

The MVP uses existing Drive PDFs. The operator runs one Codex skill, `stage-log-runs`, which checks risk before extraction. The skill calls an importer to validate JSON and stage eligible runs in SQLite. A separate review app displays the drafts alongside the source logs and records human corrections and approvals.

## 2. Status

- **[Drive inventory](https://drive.google.com/drive/folders/1q7wCJ1IxHwI8ItlhNOxSp9ZoZWkbgrn5).** Folder 1 has 152 prepared PDFs and folder 2 has 203, for 355 files. The archive addresses follow `log-1-###.pdf` and `log-2-###.pdf`. The filename index maps each address to its original file and Drive ID. A file address identifies a scan. A JC number is an optional identifier written on a run.
- **How the paper logs were scanned.** We sorted the logs into two groups. Paper logs that could feed safely through the UW paper scanner were scanned in batches grouped by log binder number. The resulting batches were split into individual PDFs. Paper logs with tape or sticky notes that could catch in the scanner were photographed with Adobe Scan. The 30 repaired Adobe PDFs preserve 35 scanned images and rendered without the original decoding errors. Each PDF contains one growth log. A growth log can contain several runs, and a run can continue across multiple scans in that PDF.
- **Extraction and storage.** [Run 01](pilot/runs/chatgpt/pdf-to-json/run01/README.md) is an unvalidated ChatGPT transcription of JC1301–JC1303. A local SQLite walkthrough stages and searches those three rows and demonstrates a reversible correction. These artifacts provide a starting point for the pilot.

## 3. MVP decisions and trade-offs

1. **Use the organized collection from Drive.** The operator uses the filename index to select existing PDFs for the skill. Preserve the originals in Drive and track each processed PDF version by its Drive file ID and file hash.
2. **Run one Codex skill for risk assessment and extraction.** The `stage-log-runs` skill checks whether the required fields are present and readable. Critical or uncertain logs wait for human clearance before extraction. The operator can retry a technical failure. The same skill extracts the measurement table once the log is eligible.
3. **Stage drafts for human review.** The skill calls the importer with its JSON output. The importer validates it and saves each draft as Pending review. A reviewer checks every draft against the source log and approves it before it enters archive search.
4. **Preserve the draft and review decision.** Keep every original extraction draft, including drafts that remain pending, and make them available to the operator and authorized reviewers in the internal review workspace. Keep each approved version with its review decision. An identical retry can reuse the existing decision.

**Extraction baseline.** Use the [Run 01 prompt](pilot/runs/chatgpt/pdf-to-json/run01/pdf-to-json-v1.text) as a starting point for the extraction stage, with the current field rules. Preserve the source PDF and retain the JSON from both stages. Convert the legacy Run 01 output before using it to test the importer.

**MVP without an API key.** The operator runs the skill in Codex using their ChatGPT subscription. The skill calls the importer after extraction, and drafts appear in the local review app. The review app displays source logs, accepts edits, and saves approvals without making model calls.

**Later model API integration.** Once approved model access is available, an automated caller can run the same risk and extraction stages and send its JSON to the same importer. Confirm PDF support, account ownership, and a spending limit before running unattended batches. Human clearance and approval rules apply to both paths.

### JSON handoff

Use the same versioned JSON format for saved Codex results and automated model results. Each packet covers one PDF version. The operator or app adds the source and model metadata.

- Every packet includes `schema_version` (initially `1`), `stage` (`risk` or `extraction`), `pdf_id`, `file_hash`, `model`, and `prompt_version`.
- A risk packet includes `decision` (`critical`, `non_critical`, or `uncertain`) and an `issues` array. Each issue gives a reason and its source location when available. An empty array means the assessment found no issues.
- An extraction packet includes a `runs` array. Each entry has a packet-local `draft_id`, `source_locations`, and a `fields` object. Use the field keys `researcher_name`, `growth_date`, `jc_number`, `composition`, `furnace_cycle`, `furnace_layout`, `growth_process`, `timestamps`, and `measurements`.
- Each field includes `status`, `raw_value`, `value`, and `evidence`. Use `recorded`, `inferred`, `derived`, `missing`, `unreadable`, `ambiguous`, or `omitted`. Use JSON null for unknown values. Dates use `YYYY-MM` or `YYYY-MM-DD`, and JC numbers remain text as written. Evidence records a source location or explains why the value is unavailable. Each run location includes `pdf_index`, the numbered position in the source PDF starting at 1, and `row`, the data row in the measurement table. Count data rows from 1 and skip the header. Field evidence can point to a marked region in the source log.

The importer validates the packet version, required keys, and source PDF. It stages extraction drafts only for the same PDF version with a recorded non-critical assessment or human clearance. Invalid packets become technical failures. The importer matches drafts to stable run IDs where possible and avoids duplicating drafts on an identical retry. The review app records approvals separately from model output.

## 4. Workflow and ownership

This flowchart shows the MVP. The operator starts one Codex skill. The skill handles risk and extraction, the importer stages the drafts, and the review app handles human decisions and archive search.

```mermaid
flowchart TD
    A[Operator starts the Codex skill with a source PDF] --> T[Skill checks risk]
    T --> R{Risk assessment result}
    R -->|Non-critical| D[Same skill extracts the measurement table]
    R -->|Critical or uncertain| P[Human reviewer checks the original log]
    P -->|Cleared for extraction| D
    P -->|Needs resolution| Q[Hold the log before extraction]
    Q -->|Issue resolved| P
    D --> S[Importer saves pending drafts in SQLite]
    S --> G[Human reviewer checks drafts in the review app]
    G -->|Approved| K[App saves the log run in SQLite]
    G -->|Essential value unclear| I[Held - record the reason for the hold]
    I -->|More information available| G
    K --> L[Researcher searches and opens the original log]
```

1. **Operator starts the skill with existing PDFs.** Use the inventory to find the source logs and preserve their Drive file IDs and exact PDF versions.
2. **The skill assesses risk for each source log.** Check the required fields for runs in the measurement table. Use relevant source-log context to assess missing, unreadable, or ambiguous values. Issues confined to the lower table do not affect the risk assessment. Save the risk tier and the evidence. Critical or uncertain logs stay on hold until a human reviewer clears them for extraction. Hold the whole PDF if any run has a critical issue. For example, a readable row still waits if another row in the same growth log has an ambiguous compound.
3. **The same skill extracts and stages drafts.** Before starting extraction, the runner checks the stored risk decision for that exact PDF version. Start extraction only if the recorded decision is non-critical or an authorized reviewer has cleared the log. If neither is recorded, wait for clearance. Once cleared, extract the measurement table. Preserve the JSON and source locations. The importer validates the JSON and saves drafts to `draft_runs` for review.
4. **Human reviewer checks each draft.** Give authorized reviewers access to open the original PDF alongside the extracted fields, manually correct individual fields, and approve the reviewed version. For each correction, save the old and new values, the reason, and the source location. Record who made the edit, who approved the version, and when. Approve a run when the reviewer can confirm a searchable value, the stoichiometry, and the source location. Hold the run before import if a required value is missing or a critical issue remains unresolved.
5. **App saves approved log runs to SQLite automatically.** The reviewer's approval triggers the save. Researchers can then search by name, date, or JC number, filter by growth process, and open the source log at the relevant row in the measurement table.

The operator starts the skill. The human reviewer clears holds and approves runs in the review app. The app saves approved runs and provides search.

**Access.** Run the MVP app on the operator’s laptop. The operator and designated reviewer can inspect drafts there. Only the designated lab-authorized reviewer can edit and approve runs. One authorized approval is required per run. Researchers can try search and source viewing during a walkthrough on the same laptop. The [pilot design](pilot/DESIGN.md) covers access from other devices.

## 5. Log Run Review and Extraction

### Risk tiers before extraction

- **Critical · Review before extraction.** Use this tier when a run has no searchable value or when an issue could attach data to the wrong run or change the scientific meaning of a core field. Examples include an uncertain row or an ambiguous compound, ratio, or unit. A human must clear the log before extraction. If a critical issue first appears in the draft, resolve it before importing the affected run. An absent or duplicate JC number is valid when the run still has a searchable value and a clear location in the original log.
- **Non-critical · Send to extraction.** Use this tier for optional details that can remain unknown without changing the core values for that log run, such as a missing layout note or an unclear timestamp when another searchable value is available. Keep the uncertainty visible in the draft.

Use real logs to check the review rules before the pilot. Include a missing JC number with another searchable value, missing stoichiometry, an ambiguous composition or unit, and a missing optional measurement.

### Fields and extraction rules

Extract run data from the measurement table of the source log. On layouts like Run 01, this is the Calculated table. Ignore the lower table. Use headers, sticky notes, and margins as context for entries in the measurement table when relevant.

| Fields | Requirement | What to extract | When to flag for review |
| --- | --- | --- | --- |
| Lookup | At least one of researcher name, date, or JC number is required. | Keep the date at its recorded precision and the JC number as written. Start and end timestamps are optional and serve only as a fallback when the date is missing. | Hold the PDF before extraction if no searchable value can be established or if ambiguity could link data to the wrong run. Hold the affected run before import if either issue remains. |
| Composition | Stoichiometry is required for import. | Keep the formula, written ratios in component order, weights and units, and distinguish calculated and measured values when both appear in the measurement table. | Hold the PDF before extraction if ambiguity could change the stoichiometry, such as an overwritten digit, unclear element symbol, or unknown ratio basis. Hold the run before import if stoichiometry is missing or unresolved, even when the run has a searchable value. |
| Furnace cycle | Optional | Capture the written cycle or graph when present, including the starting temperature, ramps, dwells, and decant temperatures. | Flag unclear temperatures, units, or graph labels in the draft and continue processing. |
| Furnace layout | Optional | Mark whether a sketch is present, absent, or unclear. When present, keep an image of the sketch with its location in the original log. | — |
| Growth process | Optional | Categorize the run as CVT (chemical vapor transport) or Flux Growth. Mark the method unclear when the evidence is inconclusive. Keep the evidence for the classification. | — |

**Dates and JC numbers.** Month and year are the minimum precision for placing a log run in chronological order. Group runs by month and preserve the exact day when it is recorded. For runs on the same date without JC numbers, sort alphabetically by researcher name, then by log run ID if names match. Where both a date and a full JC number are present, check that the JC sequence follows date order at the precision available. Flag discrepancies for review and keep both values as written. Return every match for a duplicate JC number and distinguish the runs by their source log and row in the measurement table.

If a fallback timestamp establishes a date or month, keep it as evidence and use the supported date precision for search and sorting. If the month cannot be established, flag it for review and keep the run searchable by any other available lookup value.

Some logs show only the last two digits of the JC number. Preserve them as written, including leading zeros.

**Compound carry-down.** When a compound is written once for consecutive runs in the same column, carry it down through the following blank compound cells until another compound is written or the table ends. Mark the value as carried down and point to the cell where it was written. Flag unclear boundaries for review.

**Why `x` is optional.** The log's stoichiometry can be used to calculate `x` when the composition or substitution basis is known. If the log gives elemental masses, use periodic-table atomic weights to convert the masses to moles and find the atomic ratios. When the log explicitly gives 5% substitution on the relevant site, the equivalent fraction is `x = 0.05`.

Display the raw composition with search results. Capture measurements when recorded in the measurement table. Leave load out of the MVP. Preserve the difference between an inspected blank, an unreadable entry, an ambiguous reading, an inferred value, and a value omitted by the extractor.

In the JSON draft, list missing or unclear values with the row in the measurement table or annotation in the source log so the human reviewer can check them. Check sticky notes and margins for relevant information. If a mark such as `n` is unexplained or composition notation appears in an unexpected column, preserve the written value and its location. Propose an interpretation only when the surrounding context supports it, and flag it for review.

### Furnace cycle

- **Dwell (stay)** means hold at the same temperature for a period of time. A constant temperature over an interval can indicate a dwell even if the log leaves the word out.
- **Ramp** means change from a starting temperature to a target temperature over a stated time or at a stated rate. The lab notes use room temperature as the starting condition for the first ramp. When the log says “room temperature,” keep that wording and leave the numeric value blank unless the log gives one. Leave an unstated starting condition blank.

“Ramp to 850 in 24 hours, dwell for 4 hours” means reach 850 over 24 hours, then stay at 850 for four hours. If the log gives no unit for 850, keep the value, leave its unit blank, and flag it for review. Apply the same rule to other temperatures without a stated unit.

If a log lists multiple decant temperatures, capture each one with its unit in the order written.

**Reading a furnace graph.** For a time–temperature graph, read time on the x-axis and temperature on the y-axis. Record rising segments as heating, flat segments as holds, and falling segments as cooling. If the graph shows separate left and right furnace temperatures, keep both traces and their labels. Flag unclear axes, units, or zone labels.

### CVT or Flux Growth

1. **Check for an explicit method.** Use the growth method named for that run when the rest of the log supports it or gives no conflicting evidence. If the evidence conflicts, preserve the written label and flag the classification for review.
2. **Check the table, margins, and sticky notes.** Look for a named transport agent or a note about vapor transport as CVT evidence. The lab notes give small amounts of iodine, such as 10 or 15 mg, as clues to check in context. A note about decanting residual liquid from the crystals supports flux growth.
3. **Check the furnace cycle, graph, and layout.** Two different temperatures held at the same time on opposite sides support CVT. If two temperatures have no labels, use the surrounding source log to distinguish simultaneous zones from successive steps. Heating to melt the charge, holding at high temperature, and slowly cooling toward a lower hold or decant support flux growth. Heating, holding, and cooling alone are shared clues.
4. **Check the ratio and whether the mixture could stay liquid.** Treat ratios such as 100:1 or 200:1 as supporting flux clues. Preserve the component order and ratio basis when stated. If the basis is known, identify the element with the largest atomic share and compare its pure melting point with the decant temperature or last recorded growth temperature. For a borderline case, check the phase diagram for the recorded mixture. A liquid phase at that temperature supports flux growth when the rest of the log fits.
5. **Keep uncertain cases unclear.** If the clues conflict or only weak clues are available, mark the method unclear. In the draft, point the human reviewer to the relevant parts of the original log and explain which clue is missing or conflicts.

Record how the run ended when the log gives that detail, such as shutdown, slow cooldown, crystal removal while the furnace remained on, or decanting.

## 6. Local storage

Keep the PDFs in approved Drive storage. The import packet carries a stable log run ID, the source log with the relevant row locations in the measurement table, written values, any confirmed normalized values, and the human review decision. SQLite stores the searchable fields, growth process, source reference, and review details. Use the internal log run ID as the key so duplicate, missing, or partial JC numbers can be preserved.

**MVP laptop.** Run the app locally and keep the SQLite databases and review workspaces on the operator’s laptop. Each approval applies to the draft version the reviewer opened. If that version has changed or was already approved, show the latest state before allowing any further approval. The number of PDFs required for MVP acceptance is still to be decided.

**Test and Archive environments.** Use the same app code and SQLite schema with separate databases and review workspaces. Label each environment clearly. Test uses `test.sqlite` and its own drafts, approvals, and processing status. Save the test results before resetting Test. The reset clears only Test data and leaves the source PDFs in Drive. Archive uses `archive.sqlite` for official records. The same source logs can be processed there and require fresh approval. Keep Archive data and its review history when expanding to larger batches.

**MVP backups and recovery.** Back up Archive at the end of each day with archive changes and before database migrations. Save a consistent SQLite snapshot, the review workspace, and the retained source PDF versions needed to reopen approvals. Keep backups in approved lab storage separate from the laptop. The operator checks the latest successful backup and investigates failures. Proposed targets for lab confirmation are to lose at most one day of approval and correction history and restore access by the end of the next working day.

Import a batch in one transaction. A malformed packet should leave the database unchanged. An identical reimport should create zero new rows. A changed packet for an existing log run should surface a conflict for the operator. Keep scans, private links, imported research data, and database files out of Git.

**Match runs after re-extraction.** Match each new draft to an existing run using the exact PDF version and the physical location of its entry in the measurement table. On an unchanged PDF, reuse the existing `run_id` when the match is unambiguous, even if the extractor changes its row labels. For a replaced PDF or an ambiguous location, have a reviewer compare the old and new sources and confirm whether the draft is an existing run or a new one. Keep the last approved version searchable while the match is pending.

### SQLite data model

These are the proposed MVP columns. The SQLite schema will define the final constraints and indexes.

**`source_pdfs`** has one row per version of a growth log PDF.

- `pdf_id` is the internal primary key.
- `archive_filename` is the name shown in the archive.
- `drive_file_id` identifies the original PDF in Drive.
- `file_hash` identifies the exact PDF contents. If a Drive file is replaced, keep the previous version and its source references so earlier approvals still point to the PDF the reviewer saw.
- `storage_path` locates the retained copy on the laptop when one is needed to preserve the exact PDF version.

**`draft_runs`** stores extraction drafts in the same SQLite database. Each draft has an internal ID, a source PDF ID, source locations, the original JSON, and a review status. Preserve edits and reasons for holds in the review workspace. Only reviewer approval writes a run to `growth_runs`.

**`growth_runs`** has one row per approved experimental run.

- `run_id` is the internal primary key. `pdf_id` links to `source_pdfs`. Several runs can point to the same PDF.
- `researcher_name`, `growth_date`, and `jc_number` support lookup. At least one is required. Store the JC number exactly as written, using text to preserve partial numbers and leading zeros. JC numbers can repeat across runs.
- `date_precision` records whether the date is known to the day or month. A month-only value such as `2020-01` stays at month precision.
- `growth_process` stores CVT, Flux Growth, or unclear when a classification was attempted. It supports filtering and can be empty.
- `composition_json` stores the confirmed stoichiometry, including the formula, ratios, weights, and units when available.
- `source_locations_json` stores the PDF positions and rows in the measurement table for the source log. At least one source location is required.
- `details_json` stores optional information such as furnace steps, sketch references, and evidence for the growth process.

**`run_revisions`** has one row per approved version of a run.

- `run_id` links to `growth_runs`. Together, `run_id` and `version` identify a revision.
- `approved_values_json` stores a snapshot of the approved values. `changes_json` records the fields changed, their old and new values, and the reason for each correction.
- `edited_by` and `edited_at` record who made the edit and when. These can be empty if the reviewer approved the draft as written.
- `approved_by` and `approved_at` record who approved the version and when.

An authorized reviewer can revise an existing run through the same review workflow. When the reviewer approves a run or a correction, the app saves the approved revision and the searchable run together in one SQLite transaction. Search uses the latest approved version.

Show **Saved** only after the transaction commits. If the save fails, show the error and let the reviewer retry the same approval. A retry of an already committed approval returns the saved revision without adding another one.

**Run review status.** Use **Pending review** while a draft awaits a reviewer decision. Use **Held** when a reviewer identifies an issue that must be resolved before approval. Record the reason for the hold and include the source location when available. Use **Approved** once the approved version is saved. Only approved runs enter `growth_runs` and appear in search. The associated `run_revisions` row records `approved_by` and `approved_at` and preserves any correction notes.

**`processing_status`** is a table in the same SQLite database, with one row per PDF version. Store `pdf_id`, `status`, `reason`, and `updated_at`. Distinguish PDFs held pending better evidence from technical failures that can be retried. A held PDF remains visible to the operator and can return to review when better evidence arrives. Keep pending drafts in the review workspace. Keep a PDF in review while any run still needs a decision. Approved runs from that PDF can be searchable while other runs remain pending after extraction. Report those partial outcomes alongside fully processed, held, and failed PDFs.

## 7. MVP acceptance checks

**MVP collection.** Before the acceptance test, agree with the lab on a fixed list of PDFs from the Drive inventory. Record a processing outcome for every PDF on the list. A PDF can remain held with a documented reason. Check that technical failures are visible and can be retried.

Use Run 01 as an extraction baseline. Before processing the wider batch, have a human reviewer check a small set of original PDFs and record the expected risk decisions, runs, field values, and source locations. Include both risk tiers, a PDF with multiple runs, a run continuing across multiple scans in one source log, a missing JC number with another searchable value, missing stoichiometry, and an unresolved optional detail. Reserve some PDFs for the final check after the instructions are fixed.

Plan two test rounds in Test.

1. **Walkthrough.** Run the skill on a small set of logs and verify that it stages drafts through the importer. Saved JSON can also be replayed through the importer while testing the app. Check source links, corrections, approvals, and search.
2. **Acceptance run.** Start with a clean Test workspace and use the reserved PDFs. Have an authorized reviewer verify the expected outcomes and complete the review tasks. Save the results before starting the wider batch in Archive. If a check fails, fix the issue and rerun the affected checks before expanding.

**Go/no-go for the wider batch.** Proceed once the human reviewer confirms that the final check caught every critical issue that should hold a PDF before extraction, included every expected run in the PDFs cleared for extraction, and linked each draft to the correct source log and row in the measurement table. Also verify that every test run with missing stoichiometry or an unresolved critical issue stays out of `growth_runs` and search, and that every imported run has human approval. If any check fails, fix the issue and rerun the check before expanding. Track unnecessary review holds, other extraction errors, and reviewer correction time to guide improvements.

**Researcher feedback.** Before expanding the batch, ask researchers to find an approved run and open its original log. Ask authorized reviewers to compare a draft with the PDF, correct a field, and approve it. Record where people get stuck and fix problems that prevent them from completing either task.

The MVP is ready when the team can:

- Start the skill with existing Drive PDFs and verify that eligible drafts appear in the review app without manually loading JSON.
- Verify that extraction starts for a log with a recorded non-critical decision. Verify that extraction does not start for a critical or uncertain log until an authorized reviewer records clearance for that exact PDF version.
- Confirm that pending and held drafts are visible in the review workspace, held drafts show their reason, and only approved runs enter `growth_runs` and become searchable. Verify that the saved revision identifies the approver and approval time.
- Verify that the operator can inspect pending and approved drafts internally. Have an authorized reviewer correct a field against the original PDF, approve the revision, and verify that the approved value is searchable under the same run ID with the prior value and approval history preserved.
- Find a known run by name, date or month, or JC number and open the source log at the relevant row in the measurement table. Verify that a timestamp can establish a searchable month when the date is missing. Confirm a month-only date is shown without an invented day.
- Keep missing and partial JC numbers as recorded, return all runs that share a JC number, and sort same-date runs without JC numbers alphabetically by researcher name.
- Test a source log with entries in both tables. Verify that issues in the lower table do not hold the PDF and that drafts point to the correct rows in the measurement table.
- Verify a carried-down compound against its original cell and filter reviewed runs by CVT or Flux Growth.
- Check that a furnace layout image opens from its log run and that the draft points the reviewer to unclear notation in the original log.
- Hold a searchable run before import if stoichiometry is missing or a critical issue remains unresolved. Import an approved run with an optional detail marked unresolved, such as a missing furnace temperature unit.
- Retry the same import without duplicating database entries and see a clear error for an invalid or conflicting packet.
- Re-extract an unchanged PDF with different row labels and verify that the same runs keep their IDs. Replace a PDF and verify that a reviewer must confirm the matches before any approved records change.
- Simulate a failed approval save and verify that neither the searchable run nor its revision changes. Retry the same approval and verify that it saves exactly one revision, including when a previous save committed before the app could show confirmation.
- Verify that a held PDF and a failed PDF appear as distinct outcomes and that every PDF in the MVP collection has a recorded outcome.
- Replay a saved Codex packet through the same importer and verify that it creates no duplicate drafts. Verify that invalid packets and extraction packets for uncleared logs stay out of review.
- Have the designated reviewer correct and approve a draft on the MVP laptop. Verify that a stale approval cannot overwrite a newer decision or create a duplicate revision.
- Restore an Archive backup in a separate environment. Verify that approved runs are searchable, review history is present, and source links open the exact PDF versions the reviewers saw. Record how long the restore took and how recent the restored approvals are. Compare the results with the proposed recovery targets.

[After the MVP](pilot/DESIGN.md)
