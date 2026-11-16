# Implementation Plan: Local Growth Log MVP

## Overview

This plan implements the Local Growth Log MVP described in `requirements.md` and `design.md` (both are the source of truth). It replaces the earlier task list, which predated several requirement and design changes.

The work is ordered as follows: an operator-run feasibility spike (Task 0), SQLite schema and project layout, staging tool (`risk-assess` with `--source-pdf`, `check-gate`, `stage-drafts`), `stage-log-runs` skill update, review app (core, status view, clearance, draft review, correction, hold, approval, stale protection, run revision), search, Test reset, backup and restore tooling, then the operator-run walkthrough, acceptance run, restore drill, and sign-off.

Implementation language is Python, matching the existing prototype (`pilot/sqlite/pilot.py`) and the design's staging tool. The review app uses Flask (or an equivalent minimal framework). The prototype under `pilot/` is not reused: the MVP schema replaces the pilot schema, the MVP field keys replace the pilot keys, and no MVP module imports from `pilot/`.

Phases 1 to 7 are coding tasks. Task 0, Task 8.5, and Tasks 26 to 29 are operator-run procedures that execute later, in Test only, after this plan is approved. They are included so the open items stay visible and gated. They must not touch `archive.sqlite` or run extraction on real PDFs during implementation.

---

## Tasks

## Phase 0: Pre-build Feasibility Spike

#### Task 0: Pre-build feasibility spike (operator-run, before Task 8)

**Requires:** none (0.2 uses a stub that echoes its arguments until Task 4 exists)

**Implements:** Requirements 1.1, 2.1, 3.1 (feasibility only)

The operator confirms that Codex can do what the skill depends on before the skill is built. Results go to `spike_results.md` in the workspace (git-ignored). The spike results are not acceptance evidence. Never use reserved acceptance PDFs in the spike. If any of 0.1 to 0.3 fails, stop and revisit the design before Task 8.

- [x] 0.1 Confirm Codex can run a shell command in the workspace (operator-run)
  - Ask Codex to run a command such as `python --version` and record the output and pass or fail
  - _Requirements: 1.1_

- [x] 0.2 Confirm Codex can compute a SHA-256 and call the staging tool (operator-run)
  - Ask Codex to compute the SHA-256 of one non-reserved PDF and compare it with `shasum -a 256`
  - Ask Codex to run `python staging.py` once Task 4 exists, or a stub script that echoes its arguments before then; record pass or fail
  - _Requirements: 1.1, 2.1, 3.1_

- [x] 0.3 Confirm Codex can read and assess one non-reserved PDF at adequate resolution (operator-run)
  - Record the resolution or rendering method used (for example the page render DPI) and whether the measurement table and handwriting were legible; record pass or fail
  - _Requirements: 1.1_

- [ ] 0.4 Measure time and Codex usage over three to five non-reserved PDFs (operator-run)
  - Record elapsed time and Codex usage per PDF in `spike_results.md` to plan the wider batch
  - _Requirements: 1.1_

**Verification:** `spike_results.md` records a pass or fail for 0.1 to 0.3 and the 0.4 figures, and names no reserved PDF.

---

## Phase 1: Foundation (Schema and Project Layout)

#### Task 1: Create the MVP SQLite schema

**Requires:** none

**Implements:** Requirements 1.4, 1.6, 8.5, 10.1, 10.2, 11.1, 12.1, 18.1, 24.1

Create `db/schema.sql` with the five MVP tables (`source_pdfs`, `draft_runs`, `growth_runs`, `run_revisions`, `processing_status`) exactly as specified in the design's SQLite Schema section. This replaces the pilot `growth_logs` table and `growth_log_index` view; do not reference them.

- [x] 1.1 Write `db/schema.sql`
  - `source_pdfs`: `drive_file_id TEXT NOT NULL`, `file_hash TEXT NOT NULL`, `UNIQUE(drive_file_id, file_hash)`, `storage_path`
  - `draft_runs`: `review_status` limited to `Pending review`, `Held`, `Approved`; a CHECK that a `Held` row has a non-empty `hold_reason`; index on `pdf_id`
  - `growth_runs`: `source_locations_json NOT NULL`
  - `run_revisions`: `UNIQUE(run_id, version)`; `approved_by` and `approved_at` NOT NULL
  - `processing_status`: one row per `pdf_id`; `status` limited to the five design values; `risk_decision` limited to the three decision values
  - Foreign keys with `ON DELETE RESTRICT`; callers enable `PRAGMA foreign_keys = ON`
  - _Requirements: 1.4, 1.6, 8.5, 10.1, 10.2, 11.1, 12.1, 24.1_

- [x]* 1.2 Write schema tests in `tests/test_schema.py`
  - Apply the schema to an in-memory database and assert all five tables and their columns exist
  - Assert a `source_pdfs` insert without `drive_file_id` fails and a duplicate `(drive_file_id, file_hash)` fails
  - Assert a `Held` draft with an empty or null `hold_reason` is rejected
  - _Requirements: 1.4, 10.1, 10.2_

**Verification:** `sqlite3 :memory: ".read db/schema.sql" ".tables"` lists exactly the five MVP tables, and `python -m pytest tests/test_schema.py` passes.

---

#### Task 2: Set up project layout, environment resolution, and configuration

**Requires:** Task 1

**Implements:** Requirements 1.10, 7.4, 25.1, 25.3, 26.4, 30.1

Create the layout below. `staging.py` is a thin command dispatcher; command logic lives in `staging_lib/`.

```
db/                 schema.sql, init_db.py, env.py, connect.py
common/             config.py, filename_index.py
staging.py          CLI entrypoint (risk-assess, check-gate, stage-drafts)
staging_lib/        validation and command modules
review_app/         app.py, routes/, templates/, static/, queries/
tools/              backup.py, restore.py, verify_restore.py, check_checklist.py, lookup_drive_id.py
tests/
config.json         reviewers, backup_folder (placeholder), backup_name_pattern (placeholder), filename_index_path
filename_index.json git-ignored; maps archive_filename to drive_file_id
test.sqlite, archive.sqlite   created at runtime, not committed
retained_pdfs/<environment>/  created at runtime, not committed
review_workspace/<environment>/  created at runtime, not committed
```

- [x] 2.1 Create the directory layout, package `__init__.py` files, and `.gitignore`
  - Ignore `*.sqlite`, `retained_pdfs/`, `review_workspace/`, `backups/`, JSON packets, and scans
  - Leave `pilot/` untouched
  - _Requirements: 25.1_

- [x] 2.2 Write `db/init_db.py`
  - `python db/init_db.py <database.sqlite>` applies `db/schema.sql` to a new database and exits 0
  - Refuse to run against an existing database that already has tables unless `--reset` is used (reset is implemented in Task 22)
  - _Requirements: 25.1_

- [x] 2.3 Write `db/env.py`
  - Resolve `test` or `archive` (from `--env` or an environment variable) to the database path, retained-PDF directory (`retained_pdfs/<environment>/`), and review-workspace directory
  - Reject unknown environment names
  - _Requirements: 25.1, 25.3_

- [x] 2.4 Write `config.json` and `common/config.py`
  - `reviewers` list of names; `backup_folder` and `backup_name_pattern` as null placeholders pending lab confirmation
  - `checklist_path` (default `test_checklist.json`): the file whose `acceptance` entries form the reserved list read by the reserved guard (Task 4.8)
  - Loader returns the reviewer list and `checklist_path` read-only; no code path writes the config
  - _Requirements: 7.4, 26.4, 30.1_

- [x]* 2.5 Write tests for init, environment, and config
  - `test` resolves to `test.sqlite` and `archive` to `archive.sqlite`, with distinct retained and workspace directories
  - `init_db.py` creates an empty database with all five tables
  - A scan of `staging_lib/`, `review_app/`, `db/`, and `tools/` finds no import of anything under `pilot/`
  - _Requirements: 25.1, 25.3_

- [x] 2.6 Implement the filename index and lookup tool
  - **Requires:** 2.4
  - Define `filename_index.json` (git-ignored; a JSON object mapping `archive_filename` to `drive_file_id`) and add `filename_index_path` to `config.json`; add `filename_index.json` to `.gitignore`
  - Implement `common/filename_index.py` (load the index from `filename_index_path`; look up a filename) and `tools/lookup_drive_id.py <archive_filename>`, which prints the `drive_file_id` and exits 0, or exits 1 with a message when the filename is not listed
  - Add `tests/test_lookup_drive_id.py` using a synthetic index with placeholder IDs: a listed filename prints its ID and exits 0; an unlisted filename exits 1 with a message; a missing index file exits 1 with a message
  - _Requirements: 1.10_

- [x] 2.7 Implement the shared connection helper
  - **Requires:** 2.3
  - Implement `db/connect.py` with one function that opens SQLite with `PRAGMA foreign_keys = ON`, WAL journal mode, and a 5000 ms busy timeout
  - Tasks 4.5 (`staging.py` commands) and 9.1 (`review_app/app.py`) open the database only through this helper
  - Add `tests/test_connect.py`: the pragmas are set on a new connection; two connections can read while a third holds a write transaction
  - Implementation detail from the design; no requirement criterion

**Verification:** `python db/init_db.py /tmp/check.sqlite` exits 0 and `.tables` shows the five tables; `python -m pytest tests/test_env.py` passes.

---

## Phase 2: Staging Tool

#### Task 3: Implement packet validation

**Requires:** Task 2

**Implements:** Requirements 8.5, 21.1, 21.2, 21.4, 21.5, 21.6

Write stateless validation in `staging_lib/`. Validation never opens the database, so a failure leaves it unchanged. The packet field contract is the MVP contract (`researcher_name`, `growth_date`, `jc_number`, `composition`, `furnace_cycle`, `furnace_layout`, `growth_process`, `timestamps`, `measurements`), not the pilot keys (`name`, `date`, `jc`, `technique`).

- [x] 3.1 Implement envelope validation in `staging_lib/validate_envelope.py`
  - `schema_version` present and equal to a supported version (initially `1`)
  - `stage`, `drive_file_id`, `file_hash`, `model`, `prompt_version` present and non-empty strings
  - Return a descriptive error string on failure and `None` on success
  - _Requirements: 21.1, 21.2_

- [x] 3.2 Implement risk-packet validation in `staging_lib/validate_risk.py`
  - `decision` is one of `non_critical`, `critical`, `uncertain`; `issues` is an array; each issue has a `reason` and a `source_location` that is an object or null
  - _Requirements: 21.4_

- [x] 3.3 Implement extraction-packet validation in `staging_lib/validate_extraction.py`
  - `runs` is an array; each run has non-empty `draft_id`, a non-empty `source_locations` array of `{pdf_index, row}` positive integers, and a `fields` object with all nine required keys
  - Each field has `status` (one of `recorded`, `inferred`, `derived`, `missing`, `unreadable`, `ambiguous`, `omitted`), `raw_value`, `value`, and `evidence`
  - _Requirements: 21.5_

- [x] 3.4 Implement source-PDF hash verification in `staging_lib/source_pdf.py`
  - Stream the file and compute SHA-256; return whether it equals the packet `file_hash`
  - Missing or unreadable file returns a descriptive error
  - _Requirements: 8.5, 21.6_

- [x] 3.5 Implement packet loading and error reporting in `staging_lib/packet.py`
  - Read the JSON file, report malformed JSON with a descriptive message, run envelope validation and the stage-specific validator, and map any failure to exit code 1 with nothing written
  - _Requirements: 21.1, 21.2, 21.6, 24.2_

- [x]* 3.6 Write unit tests for every validation rule in `tests/test_validation.py`
  - One test per rule, run on in-memory data only; a valid packet returns `None`
  - _Requirements: 21.1, 21.2, 21.4, 21.5, 21.6_

**Verification:** `python -m pytest tests/test_validation.py` passes; each rule violation returns a non-empty message and a valid packet returns `None`.

---

#### Task 4: Implement `risk-assess` with source-PDF verification and retained copy

**Requires:** Task 3

**Implements:** Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 4.1, 5.1, 5.5, 8.5, 14.8, 24.1, 24.2, 24.3, 30.1, 30.2, 30.3, 30.4, 30.5

Command: `python staging.py risk-assess <packet.json> --source-pdf <local path> [--acceptance-run] <database.sqlite>`. Command modules are `staging_lib/cmd_risk_assess.py`, `retain.py`, `registry.py`, and `status_store.py`.

- [x] 4.1 Create the `staging.py` dispatcher and command stubs
  - Register `risk-assess`, `check-gate`, and `stage-drafts` to modules under `staging_lib/`; later tasks fill in the stub modules without editing `staging.py`
  - `risk-assess` requires `--source-pdf`; a missing argument exits 1 with a usage message
  - _Requirements: 1.1, 8.5_

- [x] 4.2 Implement hash check and retained copy in `staging_lib/retain.py`
  - Verify the SHA-256 of `--source-pdf` equals `file_hash` before any write; a mismatch exits 1 with a message that the file bytes do not match `file_hash` and writes no rows
  - Copy the verified bytes to `retained_pdfs/<environment>/<drive_file_id>-<file_hash>.pdf` via a temporary file; never overwrite an existing retained copy
  - Return the absolute path; if the later database transaction fails, remove a copy created by this call
  - On retry for a registered version whose retained copy at `storage_path` is missing, and the `--source-pdf` hash equals `file_hash`, recreate the copy at `storage_path`; never overwrite an existing, intact copy
  - _Requirements: 1.9, 8.5_

- [x] 4.3 Implement `source_pdfs` upsert in `staging_lib/registry.py`
  - First call for a `(drive_file_id, file_hash)` pair inserts a row with `storage_path` set to the retained copy; retry reuses the existing `pdf_id` and does not change `storage_path`
  - Same `drive_file_id` with a different `file_hash` always inserts a new row
  - `archive_filename` comes from the base name of `--source-pdf`
  - _Requirements: 1.4, 1.5, 1.6, 8.5_

- [x] 4.4 Implement `processing_status` upsert in `staging_lib/status_store.py`
  - New version: insert a row with `risk_decision`, `issues_json`, and `status` (`risk_assessed` for `non_critical`; `held_pending_clearance` for `critical` or `uncertain`, with `reason` set)
  - Retry with a changed assessment result or issues: record the new `risk_decision` and `issues_json` and update `updated_at`; never change `clearance_by`, `clearance_at`, or `clearance_note`. If `status` is `cleared` or `extraction_complete`, leave `status` unchanged; otherwise `status` follows the new assessment result
  - Retry on a version whose `status` is `technical_failure`: set `status` from the stored assessment result and clearance (`held_pending_clearance`, `cleared`, `risk_assessed`, or `extraction_complete` when drafts exist) and clear `reason`
  - A new `file_hash` for the same `drive_file_id` gets a fresh row with no clearance carried over
  - `processing_status.file_hash` equals `source_pdfs.file_hash` for the same `pdf_id`
  - _Requirements: 1.5, 1.6, 1.7, 1.8, 4.1, 5.1, 5.5, 14.8_

- [x] 4.5 Wire `risk-assess` in `staging_lib/cmd_risk_assess.py`
  - Order: load and validate the packet, verify the hash, open the database through `db/connect.py` (Task 2.7), then in one transaction register the source PDF (with the retained copy) and upsert `processing_status`
  - Roll back and exit 1 with a descriptive error on any failure; on success print the number of rows staged and exit 0; never write `draft_runs` or `growth_runs`
  - _Requirements: 1.4, 24.1, 24.2, 24.3_

- [x]* 4.6 Write unit tests in `tests/test_risk_assess.py`
  - First call creates one `source_pdfs` row, one retained copy, and one `processing_status` row
  - Hash mismatch exits 1 with zero rows and no retained copy
  - Retry with the same hash writes no duplicate rows and leaves `storage_path` unchanged
  - Retry after clearance leaves `clearance_by`, `clearance_at`, and `clearance_note` unchanged
  - New `file_hash` for the same `drive_file_id` creates a new row with no clearance
  - `critical` and `uncertain` both produce `held_pending_clearance`; `non_critical` produces `risk_assessed`
  - Malformed packet writes nothing
  - Retry with the retained copy deleted and a matching `--source-pdf` recreates the copy at `storage_path`; a mismatching `--source-pdf` exits 1 and recreates nothing; an intact copy is never overwritten
  - Retry with a changed decision on a `cleared` or `extraction_complete` version records the new `risk_decision` and `issues_json` but leaves `status` and clearance fields unchanged; on a non-cleared version `status` follows the new decision
  - Retry on a `technical_failure` version sets `status` from the stored assessment result and clearance and clears `reason`
  - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 4.1, 5.1, 5.5, 8.5, 14.8_

- [ ]* 4.7 Write property test for retained copy integrity
  - **Property 10: Retained copy integrity**
  - **Requires:** 4.5
  - For generated sequences of registrations and retries (including deleted copies), every `source_pdfs` row has a retained copy at `storage_path` whose SHA-256 equals `file_hash`
  - **Validates: Requirements 1.9, 8.5**

- [x] 4.8 Implement the reserved acceptance PDF guard and wire it into `risk-assess`
  - **Requires:** 4.5, 24.1 (the checklist format)
  - Write `staging_lib/reserved_guard.py`: read the `drive_file_id` of every `acceptance` entry from the file at `checklist_path` in `config.json`
  - Apply the guard only when the database is the Test database, resolved with `db/env.py`; never apply it to the Archive database
  - Add `--acceptance-run` as an optional argument in the `staging.py` dispatcher (accepted by `risk-assess` and `stage-drafts`)
  - Call the guard in `staging_lib/cmd_risk_assess.py` before the hash check and before any retained copy. Without `--acceptance-run`, when the packet's `drive_file_id` is reserved, exit 1 with a message that the PDF is reserved for the acceptance run and write nothing. With the flag, process the PDF as usual
  - A missing checklist file or an empty `acceptance` list means no guard; print a notice that no reserved list was found
  - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5_

- [x]* 4.9 Write tests for the reserved guard in `tests/test_reserved_guard.py`
  - **Requires:** 4.8
  - Use synthetic checklists with placeholder IDs only
  - A reserved ID is rejected without the flag, with no `source_pdfs`, `processing_status`, or retained copy created; the same ID is accepted with `--acceptance-run`; a non-reserved ID is unaffected
  - An Archive database is never guarded; a missing checklist prints the notice and does not guard; an empty `acceptance` list behaves the same
  - **Property 11: Reserved PDF guard**
  - For generated reserved and non-reserved IDs on a Test database without the flag, no `source_pdfs`, `processing_status`, or `draft_runs` row exists for a reserved ID
  - **Validates: Requirements 30.2, 30.3**
  - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5_

**Verification:** Running `python staging.py risk-assess <valid_risk_packet.json> --source-pdf <fixture.pdf> test.sqlite` against a fixture PDF prints the staged-row count and exits 0, `SELECT storage_path FROM source_pdfs` returns an existing file, and the same command with a tampered fixture exits 1 with no new rows. With the fixture's `drive_file_id` listed under `acceptance` in a synthetic checklist, the command exits 1 without `--acceptance-run` and writes nothing, and exits 0 with it.

---

#### Task 5: Implement `check-gate`

**Requires:** Task 4

**Implements:** Requirements 2.1, 2.2, 2.3, 2.5, 6.5

Command: `python staging.py check-gate <drive_file_id> <file_hash> <database.sqlite>`. Read-only.

- [x] 5.1 Implement the shared gate function in `staging_lib/gate.py`
  - For the registered `(drive_file_id, file_hash)`, return cleared when `risk_decision` is `non_critical` or `clearance_by` is populated; otherwise return the reason (unknown version, held pending clearance, no assessment result)
  - Clearance is looked up only for the exact `file_hash`
  - _Requirements: 2.1, 2.3, 6.5_

- [x] 5.2 Implement the `check-gate` command in `staging_lib/cmd_check_gate.py`
  - Open the database read-only (`mode=ro`); exit 0 and print `cleared` when the gate passes; otherwise exit 1 and print the reason with the `drive_file_id` and `file_hash`
  - On exit 0, also print the absolute `source_pdfs.storage_path` of the retained copy for that version, so the skill extracts from the assessed bytes
  - _Requirements: 2.1, 2.2, 2.5_

- [x]* 5.3 Write unit tests in `tests/test_check_gate.py`
  - `non_critical` passes; `critical` without clearance fails with the held reason; `critical` with clearance passes; unknown version fails; a new `file_hash` with the same `drive_file_id` does not inherit clearance
  - The database file is byte-identical before and after every call
  - On exit 0 the output includes the absolute `storage_path` of an existing retained file; on exit 1 no path is printed
  - _Requirements: 2.1, 2.2, 2.5, 6.5_

**Verification:** `python staging.py check-gate <id> <hash> test.sqlite` exits 1 for a held version and 0 for a `non_critical` or cleared version, the exit-0 output includes the absolute path of the retained PDF, and `shasum test.sqlite` is unchanged by the call.

---

#### Task 6: Implement `stage-drafts`

**Requires:** Tasks 3, 4, 5

**Implements:** Requirements 2.3, 2.4, 3.4, 3.5, 4.3, 5.3, 14.7, 14.8, 21.3, 22.1, 22.2, 23.1, 23.2, 24.1, 24.2, 24.3, 30.2, 30.3, 30.4

Command: `python staging.py stage-drafts <packet.json> [--acceptance-run] <database.sqlite>`. Modules: `stage_drafts_prechecks.py`, `draft_store.py`, `failure_record.py`, `cmd_stage_drafts.py`.

- [x] 6.1 Implement version lookup and gate in `staging_lib/stage_drafts_prechecks.py`
  - Look up `pdf_id` from `(drive_file_id, file_hash)` in `source_pdfs`; if absent, exit 1 with a message that `risk-assess` must complete for that version first
  - Apply the shared gate from Task 5; on failure exit 1 with a message naming `drive_file_id` and `file_hash` and the missing clearance, with no rows written
  - _Requirements: 2.3, 2.4, 21.3_

- [x] 6.2 Implement draft insert, idempotency, and conflict detection in `staging_lib/draft_store.py`
  - Look up each run by `pdf_id` and `draft_id`; insert new runs as `Pending review` with `source_locations_json`, `original_json`, and `updated_at`
  - Identical content: skip without error; different content: report the `draft_id` and both JSON payloads, exit 1, and roll back the batch
  - A `draft_id` that already exists under a different `pdf_id` is reported as a conflict (see Notes)
  - _Requirements: 3.4, 22.1, 22.2, 23.1, 23.2_

- [x] 6.3 Implement technical-failure recording in `staging_lib/failure_record.py`
  - Record only when a command fails with an unexpected processing error (such as a file copy or database error) after packet validation has passed and the version is already registered in `source_pdfs`. Roll back the command's own writes first, then record `status = technical_failure` and a non-empty `reason` in `processing_status` in a separate transaction that does not touch `draft_runs`, `growth_runs`, or `run_revisions`
  - A validation failure, a conflict, a gate rejection, or an unregistered version writes no rows, including to `processing_status`; the command only reports the error and exits 1
  - Test both paths: an injected file-copy or database error on a registered version produces one `technical_failure` row and no other changes; a validation failure, conflict, and gate rejection leave `shasum` of the database unchanged
  - _Requirements: 14.7, 21.6, 23.2, 24.2_

- [x] 6.4 Wire `stage-drafts` in `staging_lib/cmd_stage_drafts.py`
  - One transaction: prechecks, draft inserts, and setting `processing_status.status` to `extraction_complete` for the `pdf_id`
  - Roll back on any failure and exit 1; on success print the number of rows staged and exit 0; an identical replay stages zero rows and exits 0
  - When the version's `status` is `technical_failure`, a successful `stage-drafts` sets `status` to `extraction_complete` and clears `reason`
  - _Requirements: 3.5, 14.8, 22.1, 24.1, 24.2, 24.3_

- [x]* 6.5 Write unit tests in `tests/test_stage_drafts.py`
  - Unknown PDF version rejected; extraction without clearance rejected; extraction after `non_critical` inserts `Pending review` rows and sets `extraction_complete`; extraction after clearance succeeds
  - Identical replay stages zero rows; changed packet reports a conflict and leaves `draft_runs` unchanged; a mid-batch failure leaves the database unchanged
  - A held, uncleared version has zero `draft_runs` rows after a rejected `stage-drafts`; a `non_critical` version whose `issues` array lists lower-table issues is still accepted without clearance
  - A successful `stage-drafts` on a `technical_failure` version sets `extraction_complete` and clears `reason`
  - _Requirements: 2.3, 2.4, 3.4, 3.5, 4.3, 5.3, 14.8, 21.3, 22.1, 22.2, 23.1, 23.2, 24.2_

- [ ]* 6.6 Write property test for the extraction gate
  - **Property 1: Extraction gate**
  - For generated database states and packets with neither a `non_critical` assessment result nor a clearance for the exact `drive_file_id` and `file_hash`, `stage-drafts` exits non-zero and writes zero rows
  - **Validates: Requirements 2.3, 2.4**

- [ ]* 6.7 Write property test for idempotent import
  - **Property 3: Idempotent import**
  - Importing the same generated packet twice stages zero rows the second time and exits 0
  - **Validates: Requirements 22.1, 22.2**

- [ ]* 6.8 Write property test for conflict rejection
  - **Property 4: Conflict rejection**
  - A generated packet reusing an existing `draft_id` with different content exits non-zero and leaves `draft_runs` unchanged
  - **Validates: Requirements 23.1, 23.2**

- [x] 6.9 Wire the reserved guard and `--acceptance-run` into `stage-drafts`
  - **Requires:** 4.8, 6.4
  - Call the guard from `staging_lib/reserved_guard.py` at the start of `staging_lib/cmd_stage_drafts.py`, before any database write: without the flag a reserved `drive_file_id` exits 1 with the reserved message and writes nothing; with the flag the PDF is processed as usual
  - Confirm `staging_lib/cmd_check_gate.py` does not call the guard, since `check-gate` is read-only
  - Add tests to `tests/test_reserved_guard.py` (synthetic checklist, placeholder IDs): a reserved ID is rejected by `stage-drafts` without the flag with zero `draft_runs` rows; accepted with the flag; `check-gate` returns the same result for a reserved ID with or without a checklist; an Archive database is never guarded
  - _Requirements: 30.2, 30.3, 30.4_

**Verification:** After `risk-assess` records `non_critical`, `python staging.py stage-drafts <packet.json> test.sqlite` exits 0, `SELECT review_status FROM draft_runs` returns `Pending review` for each run, and `SELECT status FROM processing_status` returns `extraction_complete`. Replaying the packet exits 0 with no new rows. Running it against a held, uncleared version exits 1 naming the `drive_file_id`.

---

#### Task 7: Checkpoint - staging tool

**Requires:** Tasks 3, 4, 5, 6

- [x] 7. Checkpoint - Ensure all tests pass, ask the user if questions arise.
  - Run `python -m pytest tests/test_schema.py tests/test_validation.py tests/test_risk_assess.py tests/test_check_gate.py tests/test_stage_drafts.py`.

---

## Phase 3: Codex Skill (`stage-log-runs`)

#### Task 8: Update the `stage-log-runs` skill instructions

**Requires:** Tasks 0.1, 0.2, 0.3, 2.6, 4, 5, 6

**Implements:** Requirements 1.1, 1.2, 1.3, 1.10, 1.11, 2.1, 2.2, 3.1, 3.2, 3.3, 4.2, 4.3, 5.2, 5.3, 5.4, 6.4, 2.5, 30.7

Update `.agents/skills/stage-log-runs/SKILL.md`. Read the existing file first and keep what is still correct.

- [x] 8.1 Update the risk-assessment section
  - Before `risk-assess`, run `python tools/lookup_drive_id.py <archive_filename>` to obtain `drive_file_id`; if it exits 1 (filename not listed) stop and tell the operator
  - Set `model` in each packet to the model name Codex reports or, if Codex cannot report one, a value the operator supplies; set `prompt_version` to the version stated in `SKILL.md`; never leave either blank
  - Produce the versioned risk packet, then call `python staging.py risk-assess <packet.json> --source-pdf <local path> <database.sqlite>` automatically
  - Exit 0: report the staging result. Non-zero or tool unavailable: save the packet, report the blocker, stop, and never claim the assessment was recorded
  - Risk rules: issues confined to the lower measurement table do not raise the tier; any run with a critical or uncertain issue holds the whole PDF; do not start extraction while the PDF is held without clearance; a critical issue found after extraction is held in the review app, not by the skill
  - The lower-table rule is a skill rule: the staging tool does not classify issues (it accepts a `non_critical` packet whose issues are lower-table only, Req 4.3), so the rule is checked in the walkthrough (Task 26), not by the staging tool
  - _Requirements: 1.1, 1.2, 1.3, 1.10, 1.11, 4.2, 4.3, 5.2, 5.3, 5.4_

- [x] 8.2 Update the extraction-gate and extraction sections
  - Before extraction call `python staging.py check-gate <drive_file_id> <file_hash> <database.sqlite>`; proceed only on exit 0; otherwise stop, tell the operator reviewer clearance is required, and produce zero extraction packets
  - After clearance the operator resumes the skill on the same `drive_file_id` and `file_hash`
  - Set `model` and `prompt_version` in the extraction packet by the same rule as in 8.1, never blank
  - Produce the extraction packet and call `python staging.py stage-drafts <packet.json> <database.sqlite>` automatically; on exit 0 report the staged-row count; on failure save the packet, report the blocker, stop, and never claim drafts were staged
  - Extract from the file path that `check-gate` prints on exit 0 (the retained copy), not from any other copy of the PDF
  - While the PDF is held without clearance the skill produces zero extraction packets (Req 5.3); after clearance the operator resumes on the same `drive_file_id` and `file_hash` and `check-gate` then exits 0 (Req 6.4)
  - _Requirements: 1.11, 2.1, 2.2, 2.5, 3.1, 3.2, 3.3, 5.3, 6.4_

- [x]* 8.3 Write a lint test in `tests/test_skill_md.py`
  - Assert `SKILL.md` contains the three command lines with their exact arguments (including `--source-pdf`), the lower-table rule, the never-claim-staged rule, and the instruction to extract from the path printed by `check-gate`
  - Assert `SKILL.md` contains the `python tools/lookup_drive_id.py <archive_filename>` step with the stop-if-unlisted rule (Req 1.10), and the rule that `model` and `prompt_version` are always set and never blank (Req 1.11)
  - _Requirements: 1.1, 1.10, 1.11, 2.1, 2.5, 3.1_

- [x] 8.4 Add the acceptance-run flag to the skill instructions
  - **Requires:** 8.2, 8.3 (when implemented), 4.8
  - In `SKILL.md`, add `[--acceptance-run]` to the `risk-assess` and `stage-drafts` call lines, and state that the skill adds the flag only when the operator states the run is an acceptance run, and never otherwise
  - Update the lint test in `tests/test_skill_md.py` (Task 8.3) to assert the updated call lines and the add-only-when-stated rule
  - _Requirements: 30.7_

- [x]* 8.5 Tracer bullet in Test (operator-run, optional, informal)
  - **Requires:** 8.4, 6.9, 4.8
  - Take one non-reserved PDF through `$stage-log-runs` in Test, without `--acceptance-run`, until its draft reaches `Pending review` (check with `sqlite3 test.sqlite "SELECT review_status FROM draft_runs"`); this can be done before the review app is finished
  - Note the result in `spike_results.md` as informal; it is not acceptance evidence, and no reserved PDF is used
  - _Requirements: 1.1, 3.1, 3.4_

**Verification:** `python -m pytest tests/test_skill_md.py` passes, and an operator can follow `SKILL.md` alone to run `lookup_drive_id`, `risk-assess`, `check-gate`, and `stage-drafts` in the right order.

---

## Phase 4: Review App Core

#### Task 9: Implement the local web server and environment banner

**Requires:** Task 2

**Implements:** Requirements 25.1, 25.3, 25.4

Write `review_app/app.py` (Flask app factory). It reads the environment from `--env` or an environment variable and opens the matching database with foreign keys enabled.

- [x] 9.1 Implement app startup and database access in `review_app/app.py`
  - Resolve the environment with `db/env.py` and open the database through `db/connect.py` (Task 2.7); fail with a clear message if the database does not exist or lacks the schema
  - _Requirements: 25.1, 25.3_

- [x] 9.2 Implement the persistent environment banner in `review_app/templates/base.html`
  - Show `Test` or `Archive` on every page with distinct styling
  - _Requirements: 25.4_

- [x]* 9.3 Write tests in `tests/test_app_env.py`
  - The app opens `test.sqlite` for `test` and `archive.sqlite` for `archive`; every route response contains the environment label; two temporary databases for the two environments never share rows
  - _Requirements: 25.1, 25.3, 25.4_

**Verification:** `python review_app/app.py --env test` serves pages that show "Test" in the banner, and `python -m pytest tests/test_app_env.py` passes.

---

#### Task 10: Implement the reviewer dropdown and confirmation

**Requires:** Task 9

**Implements:** Requirements 7.1, 7.2, 7.3, 7.4

- [x] 10.1 Load reviewers from `config.json` in `review_app/reviewers.py`
  - Names come only from config; no route edits the list
  - _Requirements: 7.4_

- [x] 10.2 Implement the dropdown partial and server-side guard
  - `templates/_reviewer.html` renders the dropdown; a `require_reviewer` helper rejects any recorded action (clearance, correction, hold, approval) whose submitted name is empty or not in the config, writing nothing
  - _Requirements: 7.1, 7.3_

- [x] 10.3 Implement the confirmation partial
  - `templates/_confirm.html` shows the selected reviewer name before an action is submitted
  - _Requirements: 7.2_

- [x]* 10.4 Write tests in `tests/test_reviewer.py`
  - Each recorded-action route returns an error and writes nothing when no name or an unknown name is submitted; no route modifies the reviewer list
  - _Requirements: 7.1, 7.3, 7.4_

Implementation note: the real recorded-action routes arrive in Tasks 12 (clearance), 14 (correction), 15 (hold), and 17 (approval). Each must call `require_confirmed_reviewer` from `review_app/reviewers.py` before writing, and its tests must repeat the refusal check (no name, unknown name, nothing written). Task 10's tests use a test-only route with temporary reviewer names; the real `config.json` reviewer list stays empty until the lab supplies the authorized names.

**Verification:** `POST` to any recorded-action route without a reviewer name returns an error status and leaves the database unchanged.

---

## Phase 5: Processing Status and Clearance

#### Task 11: Implement the processing status view

**Requires:** Tasks 9, 10

**Implements:** Requirements 14.1, 14.2, 14.3, 14.5, 14.7, 10.4, 30.6

- [ ] 11.1 Implement `GET /status` in `review_app/routes/status.py` and `review_app/queries/status.py`
  - One row per `source_pdfs` version joined to `processing_status`: filename, risk tier, `status`, hold or failure `reason`
  - For PDFs that reached extraction, count `draft_runs` by `review_status` and render "N approved · N pending · N held"
  - Counts are computed on every request so they reflect each reviewer action
  - _Requirements: 14.1, 14.2, 14.3, 14.7_

- [ ] 11.2 Render the status template in `review_app/templates/status.html`
  - Show `held_pending_clearance` and `technical_failure` as visually distinct outcomes; technical failures show a retryable indication
  - Show held drafts with their hold reasons for the operator
  - Include a slot for the clearance partial (Task 12)
  - _Requirements: 14.5, 14.7, 10.4_

- [ ]* 11.3 Write tests in `tests/test_status_view.py`
  - Seed `source_pdfs`, `processing_status`, and `draft_runs` rows directly with SQL in a temporary database; do not use the hold or approval routes, so this test does not depend on Tasks 15 or 17
  - Two seeded `Pending review` rows render "0 approved · 2 pending · 0 held"; after updating one row to `Held` and one to `Approved` by SQL, the same view renders "1 approved · 0 pending · 1 held"
  - Held and technical-failure rows render distinctly with reasons
  - _Requirements: 14.1, 14.2, 14.3, 14.5, 14.7, 10.4_

- [ ] 11.4 Label reserved PDFs on the processing status view
  - **Requires:** 11.2, 4.8
  - In Test only, show "Reserved (acceptance)" beside each PDF whose `drive_file_id` is on the reserved list, reading the list through `staging_lib/reserved_guard.py` and `checklist_path`; never show the label in Archive
  - Add a test in `tests/test_status_view.py` using a synthetic checklist with placeholder IDs: the reserved PDF is labelled in Test, a non-reserved PDF is not, and no label appears in Archive or when the checklist is missing
  - _Requirements: 30.6_

**Verification:** With two `draft_runs` rows inserted by SQL as `Pending review`, `GET /status` shows "0 approved · 2 pending · 0 held"; after updating one to `Held` and the other to `Approved` by SQL it shows "1 approved · 0 pending · 1 held".

---

#### Task 12: Implement reviewer clearance

**Requires:** Tasks 5, 6, 10, 11

**Implements:** Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 14.4, 1.6, 7.2

- [ ] 12.1 Implement `POST /status/<pdf_id>/clear` in `review_app/routes/clearance.py`
  - Allowed only when `status` is `held_pending_clearance`; requires a reviewer name and a non-empty clearance note
  - Write `clearance_by`, `clearance_at`, `clearance_note`, set `status` to `cleared`, and update `updated_at`, all on the exact `pdf_id` row so a new `file_hash` is never cleared by an older version's clearance
  - _Requirements: 6.2, 6.3, 6.5, 1.6_

- [ ] 12.2 Implement the clearance prompt in `review_app/templates/_clearance.html`
  - For held PDFs show the issues from `issues_json`, the reviewer dropdown, the confirmation with the selected name, and a note to resume the skill on the same PDF version
  - _Requirements: 6.1, 6.4, 14.4, 7.2_

- [ ]* 12.3 Write tests in `tests/test_clearance.py`
  - Clearance without reviewer or note is rejected; a valid clearance sets the three fields and `cleared`
  - After clearance `python staging.py check-gate` exits 0 for that version and `stage-drafts` accepts its packet
  - A replacement version (same `drive_file_id`, different `file_hash`) is not cleared and needs its own `risk-assess` and clearance
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 1.6_

**Verification:** Submitting clearance with a reviewer and note on a held PDF changes its status to `cleared`, and `python staging.py check-gate <id> <hash> test.sqlite` then exits 0.

---

## Phase 6: Draft Review, Correction, Hold, Approval

#### Task 13: Implement the draft list, draft detail, and source-PDF viewer

**Requires:** Tasks 9, 10

**Implements:** Requirements 3.4, 8.1, 8.2, 8.3, 8.4, 8.6, 10.3, 27.7

- [ ] 13.1 Implement `GET /drafts` in `review_app/routes/drafts.py`
  - List `Pending review` and `Held` drafts with `pdf` filename, source location, status, and hold reason
  - _Requirements: 3.4, 10.3_

- [ ] 13.2 Implement `GET /drafts/<draft_id>`
  - Show every field from `original_json` with `status`, `raw_value`, `value`, and `evidence`, beside the source-PDF viewer panel
  - _Requirements: 8.1_

- [ ] 13.3 Implement the PDF viewer route in `review_app/routes/pdf.py` and `templates/_pdf_panel.html`
  - Serve the file at `source_pdfs.storage_path` and open it at the recorded page (`#page=<pdf_index>`); show the measurement-table row number as a label beside the viewer because browsers cannot scroll to a row (Req 8.2; this is how the app opens the source "at the expected page and row" in DESIGN-MVP.md section 7)
  - If the path does not resolve to a readable file, show the error in the viewer panel and keep the rest of the page usable
  - When the PDF is opened, compare the SHA-256 of the retained copy with `file_hash` in `review_app/pdf_integrity.py`; on a mismatch show a warning in the viewer panel and mark that PDF as blocked for approval of its drafts until the copy is restored
  - _Requirements: 8.2, 8.3, 8.6_

- [ ] 13.4 Show every recorded source location in `templates/_pdf_panel.html`
  - A run spanning pages lists all `source_locations_json` entries, each opening the viewer at its page and row
  - _Requirements: 8.4_

- [ ]* 13.5 Write tests in `tests/test_draft_detail.py`
  - The viewer link carries the recorded page (`#page=<pdf_index>`) and the recorded row number is rendered as a label beside the viewer
  - Pending and held drafts are listed; detail shows fields and evidence; a missing `storage_path` file shows an error panel but the page loads; multiple locations are all reachable
  - A retained copy whose SHA-256 differs from `file_hash` shows a warning in the viewer panel and marks the PDF blocked for approval
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_

- [ ] 13.6 Add the furnace layout source-location action
  - **Requires:** 13.3, 19.1
  - On the draft detail and on the run detail (`review_app/routes/run_detail.py`), add an action beside the `furnace_layout` field that opens the source PDF at that field's source location, using the viewer and integrity check from 13.3
  - Add a test in `tests/test_layout_open.py` that the action links to the recorded page and row from both views
  - _Requirements: 27.7_

**Verification:** Opening a draft shows its fields and the PDF at the recorded page; deleting the retained file shows an error in the viewer panel while the page still loads.

---

#### Task 14: Implement field correction

**Requires:** Tasks 10, 13

**Implements:** Requirements 7.1, 9.1, 9.2, 9.3, 9.4

Pending corrections are stored outside `draft_runs.original_json` (see Notes).

- [ ] 14.1 Implement the correction store in `review_app/corrections.py`
  - Append corrections per draft as JSON under `review_workspace/<environment>/corrections/<draft_id>.json`, each with field, old value, new value, reason, source-location reference, reviewer, and timestamp
  - Never modify `original_json`
  - _Requirements: 9.2, 9.3_

- [ ] 14.2 Implement the edit form and route in `review_app/routes/corrections.py`
  - Require a reason and a reviewer name before saving; reject otherwise
  - _Requirements: 9.1, 9.4, 7.1_

- [ ] 14.3 Implement effective values in `review_app/effective.py`
  - Merge `original_json` with corrections to produce the values shown in detail and used for approval; saving a correction updates `draft_runs.updated_at` so stale protection sees it
  - _Requirements: 9.2, 9.3_

- [ ]* 14.4 Write tests in `tests/test_corrections.py`
  - `original_json` is byte-identical after a correction; a correction without a reason or reviewer is rejected; the stored record has old value, new value, reason, and source location
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

**Verification:** After saving a correction, `SELECT original_json FROM draft_runs WHERE draft_id = ?` returns the unmodified extraction, and the correction file records the old value, new value, reason, and source location.

---

#### Task 15: Implement the hold workflow and held-draft reopening

**Requires:** Tasks 10, 13, 14

**Implements:** Requirements 5.4, 10.1, 10.2, 10.3, 10.4, 10.5

- [ ] 15.1 Implement `POST /drafts/<draft_id>/hold` in `review_app/routes/hold.py`
  - Require a reviewer name and a non-empty `hold_reason` (with an optional source location); set `review_status = 'Held'`, store the reason, update `updated_at`; reject an empty reason with a 400 and no change
  - A critical issue found during review is recorded this way and never reaches `growth_runs`
  - _Requirements: 5.4, 10.1, 10.2_

- [ ] 15.2 Implement the held-draft view
  - A held draft shows its hold reason and still allows editing, saving a correction, and re-attempting approval; it stays `Held` (and out of search) until approved
  - _Requirements: 10.3, 10.5_

- [ ]* 15.3 Write tests in `tests/test_hold.py`
  - Hold without a reason is rejected; hold with a reason sets status and reason; a held draft appears in `/status` with its reason and in no search result and no `growth_runs` row; a held draft can take a correction
  - _Requirements: 5.4, 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ]* 15.4 Write property test for hold reason
  - **Property 5: Hold reason required**
  - For generated hold requests, every `Held` row has a non-empty `hold_reason`, and requests with empty or whitespace reasons leave the row unchanged
  - **Validates: Requirements 10.1, 10.2**

**Verification:** `POST /drafts/<id>/hold` with an empty reason returns 400 and leaves `review_status` unchanged; with a reason, `review_status` is `Held` and `hold_reason` is set.

---

#### Task 16: Implement approval preconditions

**Requires:** Tasks 13, 14

**Implements:** Requirements 7.2, 8.6, 11.1, 11.2, 11.3, 11.4

- [ ] 16.1 Implement precondition checks in `review_app/preconditions.py`
  - On effective values: at least one `source_locations_json` entry with a valid page and row; at least one of `researcher_name`, `growth_date`, `jc_number` populated; `composition_json` populated with a non-null stoichiometry value
  - Stoichiometry is a hard gate with no bypass; return the list of unmet conditions
  - Reject approval while the draft's PDF fails the retained-copy check from `review_app/pdf_integrity.py` (Task 13.3); report it as an unmet condition
  - _Requirements: 8.6, 11.1, 11.2, 11.3_

- [ ] 16.2 Implement the approval confirmation page
  - `GET /drafts/<draft_id>/approve` lists unmet conditions, disables the approve button, and offers Hold or Return to editing; when all pass it shows the reviewer name for confirmation
  - _Requirements: 11.4, 7.2_

- [ ]* 16.3 Write tests in `tests/test_preconditions.py`
  - Each condition fails independently; all three failing yields three messages; a forged approve POST with missing stoichiometry is rejected server-side
  - A draft whose PDF has a retained copy with a mismatching SHA-256 cannot be approved, including by a direct POST, and approval works again after the copy is restored
  - _Requirements: 8.6, 11.1, 11.2, 11.3, 11.4_

**Verification:** A draft with null `composition` shows the stoichiometry error, the approve button is disabled, and a direct POST to approve is rejected.

---

#### Task 17: Implement the atomic approval transaction

**Requires:** Task 16

**Implements:** Requirements 11.1, 11.2, 11.3, 12.1, 12.2, 12.3, 12.4

`run_id` is derived deterministically from `draft_id` (see Notes) so a retry can detect an already-committed approval.

- [ ] 17.1 Implement the approved-values mapper in `review_app/approval_mapper.py`
  - Build the `growth_runs` row (searchable columns, `date_precision`, `composition_json`, `details_json`) and the `run_revisions` snapshot from effective values, including `changes_json` and `edited_by`/`edited_at` when corrections exist
  - _Requirements: 12.1_

- [ ] 17.2 Implement `POST /drafts/<draft_id>/approve` in `review_app/routes/approve.py`
  - Re-run the preconditions, then one `BEGIN IMMEDIATE` transaction: insert `growth_runs`, insert `run_revisions` (next `version`, `approved_by`, `approved_at`, snapshot, corrections), set `draft_runs.review_status = 'Approved'`
  - For a revision of an already approved run (Task 19), update the searchable columns of the existing `growth_runs` row instead of inserting one
  - _Requirements: 12.1, 11.1, 11.2, 11.3_

- [ ] 17.3 Implement result reporting
  - Show "Saved" only after the commit; on failure show the error and leave the form editable with `growth_runs` and `run_revisions` unchanged
  - _Requirements: 12.2, 12.3_

- [ ] 17.4 Implement idempotent retry
  - If the draft's `run_id` and `version` already exist, return the saved revision without inserting a duplicate
  - _Requirements: 12.4_

- [ ]* 17.5 Write tests in `tests/test_approval.py`
  - A valid approval inserts exactly one `growth_runs` row and one `run_revisions` row with approver and timestamp; a failure injected after the `growth_runs` insert leaves both tables unchanged; a retry of a committed approval returns the existing revision
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ]* 17.6 Write property test for atomic approval
  - **Property 2: Atomic approval**
  - After any generated sequence of approvals and failures, every `growth_runs` row has a matching `run_revisions` row with non-null `approved_by` and `approved_at`
  - **Validates: Requirements 12.1**

- [ ]* 17.7 Write property test for failed transaction atomicity
  - **Property 9: Failed transaction atomicity**
  - A failure injected at any point inside the approval transaction leaves `growth_runs` and `run_revisions` unchanged
  - **Validates: Requirements 12.3**

- [ ]* 17.8 Write property test for approved run completeness
  - **Property 6: Approved run completeness**
  - Every `growth_runs` row produced by generated approvals has at least one source location, at least one of `researcher_name`, `growth_date`, `jc_number`, populated `composition_json`, and a matching `run_revisions` row
  - **Validates: Requirements 11.1, 11.2, 11.3, 12.1**

**Verification:** Approving a valid draft inserts one row in `growth_runs` and one in `run_revisions`; `SELECT approved_by, approved_at FROM run_revisions` returns the reviewer and a timestamp; a forced mid-transaction error leaves both tables empty.

---

#### Task 18: Implement stale-approval protection

**Requires:** Task 17

**Implements:** Requirements 13.1, 13.2

- [ ] 18.1 Capture state when the reviewer opens the draft
  - Always capture `draft_runs.updated_at`; capture `run_revisions.version` only when the run already has a revision; carry both in the approval form
  - _Requirements: 13.1_

- [ ] 18.2 Compare inside the approval transaction
  - Read the current `updated_at` (and `version` when a revision exists) before writing; if either changed, abort without writing, reload the latest state, and require the reviewer to confirm before approval proceeds
  - _Requirements: 13.1, 13.2_

- [ ]* 18.3 Write tests in `tests/test_stale_approval.py`
  - A changed `updated_at` (for example after a hold or correction) forces reload and confirmation; a first approval with no revision does not read `version`; a changed `version` forces confirmation
  - _Requirements: 13.1, 13.2_

- [ ]* 18.4 Write property test for stale approval safety
  - **Property 8: Stale approval safety**
  - A generated approval carrying an older `updated_at` or `version` never overwrites a revision with a higher version and never inserts a duplicate revision
  - **Validates: Requirements 13.1, 13.2**

**Verification:** Opening a draft, holding it from a second session, then submitting the first session's approval shows the latest state and writes nothing until confirmed.

---

#### Task 19: Implement the run revision view and revise workflow

**Requires:** Tasks 17, 18; 19.3 also uses the query builder from 21.1

**Implements:** Requirements 9.1, 9.2, 9.3, 9.4, 11.4, 12.1, 13.1, 29.1, 29.2, 29.3, 29.4, 29.5

- [ ] 19.1 Implement `GET /runs/<run_id>` in `review_app/routes/run_detail.py`
  - Show the approved run and its `run_revisions` in version order, with `changes_json` old and new values, `edited_by`, `approved_by`, and `approved_at`
  - _Requirements: 12.1_

- [ ] 19.2 Implement `POST /runs/<run_id>/revise` in `review_app/routes/revise.py`
  - Start a correction from the latest approved values; require a reviewer name, a reason for each change, and the approval preconditions; reuse the correction store, preconditions, approval transaction, and stale check
  - In one transaction insert the `run_revisions` row with version N+1 and update the searchable columns of the same `growth_runs` row; earlier `run_revisions` rows stay unchanged
  - A stale view applies the stale-approval protection from Task 18; a failed transaction leaves `growth_runs` and `run_revisions` unchanged
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 11.4, 12.1, 13.1, 29.1, 29.2, 29.4, 29.5_

- [ ]* 19.3 Write tests in `tests/test_revisions.py`
  - Approve then revise produces versions 1 and 2 with the earlier revision byte-identical; the revise path enforces reviewer name, reason, and preconditions
  - A revise from a stale view requires confirmation and writes nothing until confirmed; an injected failure inside the revision transaction leaves `growth_runs` and `run_revisions` unchanged
  - After a revision commits, the search query builder returns the revised value for the same `run_id`
  - _Requirements: 9.1, 9.4, 12.1, 29.1, 29.2, 29.3, 29.4, 29.5_

**Verification:** After approving and revising a run, `SELECT version, approved_by FROM run_revisions ORDER BY version` returns both rows and search returns the revised value.

---

#### Task 20: Checkpoint - review app

**Requires:** Tasks 9 to 19

- [ ] 20. Checkpoint - Ensure all tests pass, ask the user if questions arise.
  - Run `python -m pytest tests/` for the review app suites.

---

## Phase 7: Search

#### Task 21: Implement approved-run search

**Requires:** Tasks 17, 19.1; the revised-value check in 21.5 also uses 19.2

**Implements:** Requirements 8.2, 8.6, 10.3, 14.6, 15.1, 15.2, 15.3, 16.1, 16.2, 16.3, 17.1, 17.2, 17.3, 17.4, 17.5, 18.1, 18.2, 19.1, 19.2, 19.3, 19.4, 20.1, 20.2, 20.3, 20.4

Search queries `growth_runs` only and never reads `draft_runs`.

- [ ] 21.1 Implement the query builder in `review_app/search/query.py`
  - Researcher name: case-insensitive substring, usable alone
  - Month `YYYY-MM`: `growth_date` prefix match (month-only and day-precision); exact date `YYYY-MM-DD`: equality; each usable alone
  - Name and month together: both conditions (AND); no match returns an empty set
  - JC number: equals the value or contains it as a substring of the stored as-written value; all matches returned
  - Growth-process filter: `CVT`, `Flux Growth`, `unclear`, or `any` (no filter)
  - _Requirements: 15.1, 15.2, 16.1, 16.2, 16.3, 17.1, 17.2, 17.3, 18.1, 18.2, 19.1, 19.3_

- [ ] 21.2 Implement ordering and display in `review_app/search/ordering.py`
  - Chronological by `growth_date`, with a month-only value before day-precision values in the same month; month-only dates display without an invented day
  - Same date, no JC number: `researcher_name`, then `run_id`; same date and same non-null JC number: `run_id`
  - Each result shows its source PDF filename and measurement-table row so runs sharing a JC number can be told apart
  - _Requirements: 17.4, 17.5, 19.2, 20.1, 20.2_

- [ ] 21.3 Implement `GET /runs` in `review_app/routes/search.py` and `templates/search.html`
  - Search form (name, month, exact date, JC number, growth process) and results list built from 21.1 and 21.2
  - _Requirements: 15.1, 15.2, 16.3, 17.3_

- [ ] 21.4 Add the "Open source PDF" action to each result
  - Open the retained PDF from `source_pdfs.storage_path` at the page in the run's `source_locations_json` and show the recorded measurement-table row number as a label beside the viewer, reusing the viewer and the SHA-256 integrity check from Task 13.3 (warning in the viewer panel on mismatch)
  - _Requirements: 8.2, 8.6, 20.3, 20.4_

- [ ]* 21.5 Write tests in `tests/test_search.py`
  - Name alone, month alone, exact date, combined name and month, JC substring, shared JC returning all runs, growth-process filter, and sort order including the shared-JC `run_id` rule
  - JC numbers stay text as written: a two-digit partial (for example `06`) and a value with a leading zero are stored and displayed unchanged through staging, correction, and approval, and a JC number reused by another run is accepted (Req 19.4)
  - Pending and held drafts never appear; approved runs from a PDF are searchable while other drafts from that PDF stay pending or held; a run with an unresolved critical issue does not appear
  - After a revision (Task 19.2) search returns the revised value for the same `run_id`; a result's "Open source PDF" action shows the integrity warning for a tampered retained copy
  - A result's "Open source PDF" action opens the viewer at the recorded page and renders the recorded row number as a label beside it
  - _Requirements: 8.2, 10.3, 14.6, 15.2, 15.3, 16.1, 17.1, 17.2, 17.4, 17.5, 18.1, 19.1, 19.2, 19.3, 19.4, 20.1, 20.2, 20.3, 20.4_

- [ ]* 21.6 Write property test for search isolation
  - **Property 7: Search isolation**
  - For generated database states mixing `draft_runs` and `growth_runs`, every search result's `run_id` exists in `growth_runs` and no `draft_runs` row is returned
  - **Validates: Requirements 15.1, 15.2, 15.3**

**Verification:** With two approved runs and one pending draft in `test.sqlite`, `GET /runs?name=Alice` returns only Alice's approved runs and `GET /runs?month=2024-03` returns month-only and day-precision runs from that month, with the pending draft absent.

---

## Phase 8: Test Reset and Backup Tooling

#### Task 22: Implement Test environment reset

**Requires:** Task 2

**Implements:** Requirements 25.2, 25.5, 27.4

- [ ] 22.1 Implement `python db/init_db.py test.sqlite --reset`
  - Delete and recreate `test.sqlite` with the MVP schema, and clear `retained_pdfs/test/` and `review_workspace/test/`
  - Refuse any path or environment other than Test; never touch `archive.sqlite`, `config.json`, or Drive PDFs
  - Require an explicit confirmation that walkthrough or acceptance results were saved first
  - _Requirements: 25.2, 25.5, 27.4_

- [ ]* 22.2 Write tests in `tests/test_reset.py`
  - Using temporary directories: reset empties Test data and leaves a sibling archive database, retained archive PDFs, and config byte-identical; reset against an Archive path is refused; reset without confirmation is refused
  - _Requirements: 25.2, 25.5_

**Verification:** `python -m pytest tests/test_reset.py` passes, and the tests never open the real `archive.sqlite`.

---

#### Task 23: Implement backup, restore, and restore-verification tooling

**Requires:** Task 2 for 23.1, 23.2, 23.5; Tasks 11 and 21 for 23.3, 23.4, 23.6

**Implements:** Requirements 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7

The backup folder path, naming convention, and recovery targets are not confirmed by the lab. Build the tooling with configurable placeholders and do not hard-code them.

- [ ] 23.1 Implement `tools/backup.py`
  - `python tools/backup.py snapshot --env <env> [--dest <folder>] [--reason <label>]` uses SQLite's backup API for a consistent snapshot, and copies the review workspace and the retained PDF versions needed to reopen approvals
  - The destination comes from `config.json` `backup_folder` (null placeholder) or `--dest`; with neither, refuse with a message that the lab has not confirmed a folder
  - Record the timestamp of the last successful backup in a local status file; on failure exit non-zero, record the failure, and leave the last-success value unchanged
  - Support `--reason pre-migration` so the snapshot can be taken before any database migration
  - _Requirements: 26.1, 26.2, 26.3, 26.4_

- [ ] 23.2 Implement `tools/restore.py`
  - Restore a snapshot, its workspace, and retained PDFs into a separate Test workspace (for example `test_restore.sqlite`); refuse to restore over `archive.sqlite`
  - _Requirements: 26.7_

- [ ] 23.3 Implement `tools/verify_restore.py`
  - Against the restored database: run the search query builder to confirm approved runs are searchable, confirm `run_revisions` history is present, confirm each `storage_path` exists and its SHA-256 equals `file_hash`
  - Report the elapsed restore time and the age of the newest restored approval so they can be compared with the lab's targets
  - _Requirements: 26.5, 26.6, 26.7_

- [ ] 23.4 Show the last successful backup on the status view
  - Add the last-backup timestamp and any recorded failure to `GET /status`
  - _Requirements: 26.3_

- [ ]* 23.5 Write tests for backup and restore in `tests/test_backup_restore.py`
  - Use temporary databases only: a snapshot opens and matches the source; a missing destination is refused; a failed backup does not advance the last-success timestamp; restore into a separate path leaves the source untouched and refuses an Archive target
  - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.7_

- [ ]* 23.6 Write tests for restore verification in `tests/test_verify_restore.py`
  - A restored database with approved runs, revisions, and valid retained PDFs passes; a missing PDF or hash mismatch fails
  - _Requirements: 26.7_

**Verification:** `python -m pytest tests/test_backup_restore.py tests/test_verify_restore.py` passes using temporary directories, and `python tools/backup.py snapshot --env test` refuses to run while `backup_folder` is null.

---

## Phase 9: Test Checklist and Operator-Run Tests

#### Task 24: Implement the Test checklist template and validator

**Requires:** Task 2

**Implements:** Requirements 27.1, 27.2, 27.5, 27.7, 27.8, 27.9, 27.10, 28.1, 28.2, 28.3, 28.8, 28.12, 28.13, 28.14

- [ ] 24.1 Create `test_checklist.json` (empty template, no PDFs named)
  - Separate `walkthrough` and `acceptance` lists; each entry keyed by `filename`, `drive_file_id`, and `file_hash`
  - Acceptance entries also hold expected risk tier, expected hold reason, expected run count, per-run source page and row, expected name, date, JC number, stoichiometry where readable, expected approve or hold status, search terms, `expected_recorded_by`, `expected_recorded_at`, and `expected_hold_stage` (`before_extraction`, `in_review`, or null); an optional `first_run_at` is filled when the run starts
  - Add a top-level `tool_versions` record (skill, staging tool, review app) and a `feedback` record (researcher and reviewer tasks, where people got stuck, problems that prevented completion)
  - Walkthrough entries list the missing-information cases (Req 27.2) and structural cases (Req 27.10) they cover, flag whether the PDF has a furnace layout sketch, and, for a critical-case PDF, name its single `critical_case` (Req 27.8 (a) to (j)), its expected tier (`critical` or `uncertain`), and `one_critical_run: true` when it is the multi-run PDF with one critical run (Req 27.9)
  - A critical case with no real example is recorded as a waiver entry with `no_example_found: true` and a non-empty `waiver_reason`
  - Each acceptance entry also has result fields, null until the run: `unnecessary_holds`, `extraction_errors_found_in_review`, and `reviewer_correction_time` (Req 28.14). Numeric tolerances for these are pending Iris, so the template records values without pass or fail thresholds
  - _Requirements: 27.5, 27.7, 28.2, 28.3, 28.12, 28.13, 28.14_

- [ ] 24.2 Implement `tools/check_checklist.py`
  - Fail when an entry lacks `filename`, `drive_file_id`, or `file_hash`; when a walkthrough entry shares a `drive_file_id` with an acceptance entry; or when the walkthrough does not include Binder 1 and Binder 2 files
  - Fail when any of the nine missing-information cases in Req 27.2 is uncovered (missing researcher name, missing growth date with a usable timestamp, missing growth date without one, missing JC number, missing furnace cycle detail, missing furnace layout, missing or unclear growth process, missing timestamp, missing optional measurement)
  - Fail when any of the ten critical cases in Req 27.8 (a) to (j) has no walkthrough entry whose `critical_case` names it and that lists no other critical case; a case passes only if it has such an entry or a waiver with `no_example_found: true` and a non-empty `waiver_reason`
  - Fail when there is no multi-run entry flagged `one_critical_run: true` (Req 27.9), or when any structural case in Req 27.10 is uncovered (clear single run, multi-run all eligible, run spanning pages, carried-down compound, entries in both tables)
  - Fail when the walkthrough has no PDF flagged with a furnace layout sketch
  - Fail when an acceptance entry has no recorded expected outcome or no reviewer and timestamp, or when no acceptance entry has `expected_hold_stage = before_extraction`
  - Fail when `tool_versions` is missing or incomplete, and when `expected_recorded_at` is later than `first_run_at` for an entry that has `first_run_at` (expected outcomes must be recorded before the run)
  - With `--results`, also fail when any acceptance entry has a null `unnecessary_holds`, `extraction_errors_found_in_review`, or `reviewer_correction_time` (Req 28.14); the validator applies no numeric threshold because tolerances are pending Iris
  - The validator checks the lists only. The staging guard (Tasks 4.8 and 6.9) enforces the separation at run time in Test (Requirement 30 with 28.1)
  - _Requirements: 27.1, 27.2, 27.5, 27.7, 27.8, 27.9, 27.10, 28.1, 28.2, 28.3, 28.8, 28.12, 28.14_

- [ ]* 24.3 Write tests in `tests/test_checklist.py`
  - Each failure condition is detected on a synthetic checklist that uses placeholder IDs only; a complete synthetic checklist passes
  - Add cases for: no layout-sketch walkthrough PDF, no `before_extraction` acceptance entry, missing `tool_versions`, and `expected_recorded_at` later than `first_run_at`
  - Add a case for `--results`: null 28.14 result fields fail, filled fields pass
  - Add cases for: each critical case (a) to (j) missing; a critical entry that names two critical cases does not count for either; a waiver without a reason fails and a waiver with a reason passes; no `one_critical_run` entry; each structural case missing
  - _Requirements: 27.1, 27.2, 27.7, 27.8, 27.9, 27.10, 28.1, 28.2, 28.3, 28.8, 28.12, 28.14_

**Verification:** `python tools/check_checklist.py test_checklist.json` fails on the empty template with a list of missing items, and `python -m pytest tests/test_checklist.py` passes.

---

#### Task 25: Checkpoint - automated tests

**Requires:** Tasks 1 to 24

- [ ] 25. Checkpoint - Ensure all tests pass, ask the user if questions arise.
  - Run `python -m pytest tests/`; resolve all failures before the operator-run tasks begin.

---

#### Task 26: Walkthrough in Test (operator-run, deferred)

**Requires:** Tasks 8, 20, 21, 22, 24, 25

**Implements:** Requirements 25.2, 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7, 27.8, 27.9, 27.10, 27.11, 30.2

Runs later, in Test only, after this plan is approved.

**Open item 1 - walkthrough PDF selection (Req 27.5):** the operator picks PDFs from both Binder 1 and Binder 2 that are outside the reserved acceptance list. Filenames, Drive IDs, and version hashes must be recorded in the Test checklist before the walkthrough starts. This plan does not name PDFs. Tasks 26.2 to 26.5 cannot start until 26.1 passes.

- [ ] 26.1 Operator selects walkthrough PDFs and records them
  - Record filename, `drive_file_id`, and `file_hash` for each PDF in `test_checklist.json`; `python tools/check_checklist.py` must pass the walkthrough coverage checks (both binders, the nine missing-information cases, a dedicated PDF or a recorded waiver for each of the ten critical cases, the multi-run PDF with one critical run, the five structural cases, at least one PDF with a furnace layout sketch, no overlap with the reserved list)
  - _Requirements: 27.1, 27.2, 27.5, 27.7, 27.8, 27.9, 27.10_

- [ ] 26.2 Reset Test and start the app
  - `python db/init_db.py test.sqlite --reset`, then `python review_app/app.py --env test`; confirm the Test banner shows
  - _Requirements: 25.2, 25.4_

- [ ] 26.3 Run the walkthrough in Test
  - Run `$stage-log-runs` on each selected PDF without `--acceptance-run`; compare each assessment result with the scan
  - If a reserved acceptance PDF is selected by mistake, the staging tool rejecting it is the expected result; replace it with a non-reserved PDF
  - Practice all five actions: clear a held PDF, correct a draft, hold a draft, approve a run, and find the approved run in search
  - Cover every case listed in the checklist
  - For at least one walkthrough PDF with a furnace layout sketch, open the sketch's source location from its draft and from its approved run using the Task 13.6 action
  - Confirm the lower-table rule (Req 4.3): a PDF whose only issues are in the lower measurement table is assessed `non_critical`
  - For each critical-case PDF, confirm the skill records the expected `critical` or `uncertain` tier, the whole PDF is held, zero draft runs exist before clearance, and the review app shows a hold reason that names that case
  - For the multi-run PDF with one critical run, confirm the whole PDF is held and no draft is staged for its readable runs
  - At least once, hold a draft from a PDF that passed assessment for a critical issue first found during review, and confirm it stays out of `growth_runs` and search
  - Check the structural cases: the clear single-run PDF, the multi-run PDF, the run spanning pages (all locations recorded), the carried-down compound (draft points to the written cell), and the PDF with entries in both tables (drafts point to upper-table rows)
  - _Requirements: 4.3, 27.1, 27.2, 27.6, 27.7, 27.8, 27.9, 27.10, 27.11, 30.2_

- [ ] 26.4 Verify at least one path without manual JSON upload
  - A PDF goes through the skill's automatic `risk-assess`, `check-gate`, and `stage-drafts` calls and its draft appears as `Pending review` in the app
  - _Requirements: 27.3, 3.4_

- [ ] 26.5 Record walkthrough results before resetting Test
  - Save the checklist, staging output, and review app evidence to a file before any `--reset`
  - _Requirements: 27.4_

**Verification:** `python tools/check_checklist.py` passes walkthrough coverage, at least one draft reached `Pending review` with no manual JSON step, and the results file exists before any Test reset.

---

#### Task 27: Acceptance run in Test (operator-run, deferred)

**Requires:** Task 26

**Implements:** Requirements 25.3, 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 28.8, 28.10, 28.11, 28.12, 15.2, 15.3, 30.2, 30.3

Runs later, in Test only. The reserved list in `DESIGN-MVP.md` ("Proposed acceptance PDFs") is a proposal pending lab confirmation. `log-2-199.pdf` is a candidate only; its expected outcome, like every other expectation, is recorded by the reviewer before the run and is not fixed by this plan. An authorized reviewer confirms the reserved list, versions, and expected outcomes before the run.

- [ ] 27.1 Reviewer confirms the reserved list and records expected outcomes first
  - Record the checklist entries (filename, Drive ID, `file_hash`) and expected outcomes from the scans without using the skill's output; include at least one PDF expected to remain held and fill the coverage gaps named in `DESIGN-MVP.md`
  - `python tools/check_checklist.py` must pass the acceptance checks, and no reserved PDF appears in the walkthrough list
  - Set `expected_hold_stage = before_extraction` for at least one entry and, where the reserved set allows, `in_review` for at least one draft; do not hard-code any filename as the held PDF
  - _Requirements: 28.1, 28.2, 28.3, 28.8_

- [ ] 27.2 Reset Test, record tool versions, and run the staging pass
  - Before the run, record the skill, staging tool, and review app versions under test in `tool_versions` and reset Test with `python db/init_db.py test.sqlite --reset`
  - Run `$stage-log-runs` on each reserved PDF as an acceptance run, so the skill adds `--acceptance-run` to `risk-assess` and `stage-drafts`; compare the staging results with the checklist
  - Eligible drafts appear as `Pending review` with no manual JSON upload; a critical or uncertain PDF shows its hold reason and has zero drafts before clearance
  - Where a hold can be resolved, record clearance and rerun the same version to confirm extraction resumes; a replacement PDF gets its own assessment result
  - Test approvals are independent of Archive: no Archive database is opened
  - _Requirements: 28.1, 28.4, 28.5, 28.6, 28.12, 25.3, 30.2, 30.3_

- [ ] 27.3 Exercise review and search
  - Confirm pending and held drafts are not searchable; open a draft's source at the expected page and row, correct a field, and approve it; verify the corrected value, approver, approval time, and source link
  - Find approved runs by month alone, name alone, and both together using known expected matches; confirm a run with an unresolved critical issue does not appear
  - For each expected-approved run, find it by its recorded search terms (month alone, researcher name alone, and both together), and verify the corrected value, approver, approval time, and source link
  - A correctly recorded hold for a PDF or draft expected to stay held counts as a passing result
  - _Requirements: 28.8, 28.10, 15.2, 15.3_

- [ ] 27.4 Reviewer go/no-go confirmation
  - **Requires:** 27.3
  - The reviewer confirms and records in the results file that: every critical issue that should hold a PDF before extraction was caught; every expected run in the PDFs cleared for extraction was extracted; every draft links to the correct source PDF page and row; every run with missing or unresolved stoichiometry or an unresolved critical issue stays out of `growth_runs` and search; every imported run has human approval
  - Any failed check is fixed and rerun in Test before sign-off
  - _Requirements: 28.11_

**Verification:** Every reserved PDF has a recorded actual outcome next to its expected outcome in the checklist, every eligible draft reached `Pending review` without manual JSON upload, and at least one PDF ended in a correctly recorded hold.

---

#### Task 28: Restore drill (operator-run, deferred)

**Requires:** Tasks 23, 27

**Implements:** Requirements 26.4, 26.5, 26.6, 26.7

**Open item 2 - lab confirmation (Req 26.4 to 26.6):** the lab must confirm the backup folder path and naming convention in the shared Drive, and the recovery targets (at most one day of approvals lost; restore within one working day). The backup tooling from Task 23 works before confirmation, with `backup_folder` left as a placeholder. This task cannot be marked complete until 28.1 is done.

- [ ] 28.1 Record the lab-confirmed backup folder, naming convention, and recovery targets
  - Update `config.json` `backup_folder` and `backup_name_pattern`, and record the confirmed RPO and RTO with who confirmed them
  - _Requirements: 26.4, 26.5, 26.6_

- [ ] 28.2 Snapshot the Test database with the approved acceptance results
  - `python tools/backup.py snapshot --env test`
  - _Requirements: 26.1, 26.2, 26.3_

- [ ] 28.3 Restore into a separate Test workspace and verify
  - `python tools/restore.py` then `python tools/verify_restore.py`: approved runs searchable, revision history present, source links open the retained PDF version; record the restore duration and the age of the newest restored approval, and compare both with the confirmed targets
  - Until the Archive database holds approved records, a snapshot of the Test database with the approved acceptance results satisfies this drill
  - _Requirements: 26.5, 26.6, 26.7_

- [ ] 28.4 Record the Archive restore-drill follow-up
  - **Requires:** 28.3
  - Add an entry to the saved results file stating that the restore drill must be repeated on the first real Archive backup, with the date of the Test-snapshot drill it follows
  - _Requirements: 26.7_

**Verification:** `python tools/verify_restore.py` passes against the restored workspace, and the recorded duration and recency are compared with the lab-confirmed targets.

---

#### Task 29: Record acceptance outcomes and sign-off (operator-run, deferred)

**Requires:** Tasks 27, 28

**Implements:** Requirements 28.7, 28.9, 28.13, 28.14

- [ ] 29.1 Save acceptance evidence
  - Record every reserved PDF's outcome, each check's pass or fail, the reviewer, the restore drill result, and any discrepancy with its source location; confirm every reserved PDF has an outcome, every eligible draft reached `Pending review` without manual JSON upload, and every required approval and hold was exercised
  - Before sign-off, record feedback in the `feedback` record: ask researchers to find an approved run and open its source PDF, ask reviewers to compare a draft with its source PDF, correct a field, and approve it, and note where people got stuck and any problem that prevented completion
  - Record per reserved PDF the number of unnecessary holds, the extraction errors found in review, and the reviewer correction time, and confirm `python tools/check_checklist.py test_checklist.json --results` passes. Numeric tolerances for extraction errors and correction time are pending Iris; report the figures without a pass or fail threshold until she sets one
  - _Requirements: 28.7, 28.13, 28.14_

- [ ] 29.2 Record Iris's sign-off before wider batch processing
  - Store the sign-off with the saved results; no Archive batch processing starts before it exists
  - _Requirements: 28.9_

**Verification:** The saved results file contains an outcome for every reserved PDF and a recorded sign-off dated before any Archive batch run.

---

## Notes

- Tasks marked `*` are optional and can be skipped for a faster MVP; they do not block dependent tasks. Property tests use Hypothesis (add it as a test dependency).
- Checkpoints (Tasks 7, 20, 25) are integration gates and are not part of the dependency graph.
- Tasks 26 to 29 are operator procedures, not automated tests. They run in Test only, after this plan is approved, and never open `archive.sqlite`.
- Open items: (1) walkthrough PDF selection blocks Task 26 (Req 27.5); (2) lab confirmation of the backup folder and recovery targets blocks completion of Task 28 (Req 26.4 to 26.6).
- Confirmed by the user: technical failures (Req 14.7) are recorded in a separate transaction, only for unexpected processing errors on registered versions after validation passes (Task 6.3); `draft_id` stays the primary key with cross-PDF reuse treated as a conflict; corrections before approval are stored as JSON files in the review workspace; `run_id` is derived from `draft_id`; search sorts dates ascending; the PDF viewer opens the page and shows the row number; the three items listed under 'Out of scope' stay out.
- Deferred: matching re-extracted drafts to existing runs and reviewer confirmation for replaced PDFs (DESIGN-MVP.md section 6), and a port of the pilot `compare` command to the MVP field keys.
- The restore drill uses a snapshot of the Test database until Archive has approved records, then is repeated on the first real Archive backup (Task 28.4).
- The reserved acceptance PDF guard (Tasks 4.8, 6.9, 8.4, 11.4) is in scope. It enforces Requirement 28.1 in Test only and prevents mistakes, not misuse: it does not stop the skill from reading a scan in Codex, and a person who passes `--acceptance-run` can bypass it.
- The furnace layout source-location action (Task 13.6) and researcher and reviewer feedback (Task 29.1) are included.
- Open items remain: walkthrough PDF selection blocks Task 26; lab confirmation of the backup folder and recovery targets blocks Task 28.
- Accepted limitation (a): reviewer selection has no sign-in and is honor-system; anyone at the laptop can pick any name. Accepted for the MVP, pending lab confirmation.
- Open item (b): numeric tolerances for extraction errors and reviewer correction time (Req 28.14) are pending Iris. Tasks 24 and 29.1 record the figures without thresholds.
- Design note (c): the PDF viewer opens at the recorded page and shows the measurement-table row number as a label beside it (Req 8.2, 20.4). This is how the app opens the source at the page and row described in DESIGN-MVP.md section 7; scrolling to or highlighting the row would need position data that the JSON packet does not carry.
- (d) The Task 0 spike and the Task 8.5 tracer bullet are operator-run and informal. Their results in `spike_results.md` are not acceptance evidence, and neither uses reserved PDFs.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "0.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "0.2"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "0.3"] },
    { "id": 3, "tasks": ["2.5", "2.6", "2.7", "3.1", "3.4", "24.1", "0.4"] },
    { "id": 4, "tasks": ["3.2", "3.3", "9.1", "10.1", "22.1", "23.1", "23.2", "24.2"] },
    { "id": 5, "tasks": ["3.5", "9.2", "10.2", "13.1", "13.3", "22.2", "23.5", "24.3"] },
    { "id": 6, "tasks": ["3.6", "4.1", "9.3", "10.3", "13.2", "13.4"] },
    { "id": 7, "tasks": ["4.2", "4.3", "4.4", "10.4", "11.1", "13.5"] },
    { "id": 8, "tasks": ["4.5", "11.2", "14.1", "15.1"] },
    { "id": 9, "tasks": ["4.6", "4.8", "5.1", "11.3", "12.1", "12.2", "14.2"] },
    { "id": 10, "tasks": ["4.7", "4.9", "5.2", "6.1", "6.2", "6.3", "11.4", "14.3", "15.2"] },
    { "id": 11, "tasks": ["5.3", "6.4", "14.4", "15.3", "16.1"] },
    { "id": 12, "tasks": ["6.5", "6.6", "6.7", "6.8", "6.9", "8.1", "12.3", "15.4", "16.2", "17.1"] },
    { "id": 13, "tasks": ["8.2", "16.3", "17.2"] },
    { "id": 14, "tasks": ["8.3", "17.3"] },
    { "id": 15, "tasks": ["8.4", "17.4"] },
    { "id": 16, "tasks": ["8.5", "17.5", "17.6", "17.7", "17.8", "18.1", "19.1", "21.1", "21.2"] },
    { "id": 17, "tasks": ["13.6", "18.2", "21.3", "23.3", "23.4"] },
    { "id": 18, "tasks": ["18.3", "18.4", "19.2", "21.4", "23.6"] },
    { "id": 19, "tasks": ["19.3", "21.5", "21.6"] },
    { "id": 20, "tasks": ["26.1"] },
    { "id": 21, "tasks": ["26.2"] },
    { "id": 22, "tasks": ["26.3"] },
    { "id": 23, "tasks": ["26.4"] },
    { "id": 24, "tasks": ["26.5"] },
    { "id": 25, "tasks": ["27.1", "28.1"] },
    { "id": 26, "tasks": ["27.2"] },
    { "id": 27, "tasks": ["27.3"] },
    { "id": 28, "tasks": ["27.4"] },
    { "id": 29, "tasks": ["28.2"] },
    { "id": 30, "tasks": ["28.3"] },
    { "id": 31, "tasks": ["28.4"] },
    { "id": 32, "tasks": ["29.1"] },
    { "id": 33, "tasks": ["29.2"] }
  ]
}
```
