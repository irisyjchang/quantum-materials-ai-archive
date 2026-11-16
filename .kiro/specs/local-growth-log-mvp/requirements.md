# Requirements Document

## Introduction

The Local Growth Log MVP turns existing Drive growth-log PDFs into a searchable, human-approved crystal-growth archive running entirely on the operator's laptop. The operator invokes the `stage-log-runs` Codex skill on selected PDFs. The skill automatically calls the local staging tool (`risk-assess` and `stage-drafts`) after each corresponding packet. Any lab-authorized reviewer clears PDFs, corrects, holds, or approves drafts in the review app. Only approved runs enter `growth_runs` and appear in search. Iris signs off on the acceptance-run results before wider batch processing begins.

This document derives requirements from the approved design document (`.kiro/specs/local-growth-log-mvp/design.md`) cross-referenced against `DESIGN-MVP.md`. Requirements are not invented independently of those sources.

---

## Glossary

- **Skill**: The `stage-log-runs` Codex prompt run by the operator in ChatGPT. It is not a local CLI tool.
- **Staging_Tool**: The local Python CLI (`staging.py`) that accepts JSON packets and writes records to SQLite in a single transaction.
- **Review_App**: The local web application through which lab-authorized reviewers clear PDFs, inspect drafts alongside source PDFs, correct fields, hold, and approve runs.
- **SQLite_DB**: The single binary file on the operator's laptop that stores all MVP state.
- **SourcePDF**: One version of a growth-log PDF, identified by `drive_file_id` and `file_hash`.
- **DraftRun**: A staged extraction draft in `draft_runs`, awaiting reviewer action.
- **GrowthRun**: An approved experimental run stored in `growth_runs`.
- **RunRevision**: A versioned snapshot of an approved run stored in `run_revisions`.
- **ProcessingStatus**: The row in `processing_status` tracking risk assessment and extraction outcome per PDF version.
- **Risk_Packet**: A versioned JSON file produced by the Skill, containing the assessment result and issues array for a SourcePDF.
- **Extraction_Packet**: A versioned JSON file produced by the Skill, containing extracted run data for a cleared SourcePDF.
- **Reviewer**: A lab-authorized person who can clear PDFs, edit drafts, hold drafts, and approve runs.
- **operator**: The lab member who starts or resumes `stage-log-runs`. The operator selects source PDFs, monitors the staging tool output, and retries technical failures.
- **Extraction_Gate**: The rule that extraction may proceed only when the SourcePDF has a recorded `non_critical` assessment result or a human clearance.
- **JC_Number**: A crystal-growth experiment identifier written on a run; stored as text exactly as written.
- **Lookup_Value**: At least one of `researcher_name`, `growth_date`, or `jc_number`; required for every approved GrowthRun.
- **Stoichiometry**: The composition information recorded in `composition_json`; a hard gate for approval.
- **Test_DB**: `test.sqlite`, the SQLite database used for walkthrough and acceptance testing.
- **Archive_DB**: `archive.sqlite`, the SQLite database used for official records.

---

## Requirements

### Requirement 1: Skill invokes risk-assess automatically

**User Story:** As an operator, I want the Skill to call `risk-assess` automatically after producing a risk JSON packet, so that the assessment result is recorded without a manual JSON upload step.

#### Acceptance Criteria

1. WHEN the operator invokes the Skill with a source PDF path, the skill SHALL produce a versioned risk JSON packet and immediately call `python staging.py risk-assess <packet.json> <database.sqlite>`.
2. WHEN the staging tool returns exit code `0` from `risk-assess`, the skill SHALL report the staging result to the operator.
3. WHEN the staging tool is unavailable or returns a non-zero exit code from `risk-assess`, the skill SHALL save the completed risk JSON packet, report the blocker to the operator, and stop without claiming the assessment was recorded.
4. WHEN `risk-assess` is called for the first time for a given `drive_file_id` and `file_hash` combination, the staging tool SHALL upsert a `source_pdfs` row and a `processing_status` row in a single SQLite transaction.
5. WHEN `risk-assess` is retried with the same `drive_file_id` and `file_hash`, the staging tool SHALL reuse the existing `source_pdfs` row and update `processing_status` only if the decision has changed.
6. WHEN `risk-assess` receives a packet with the same `drive_file_id` but a different `file_hash`, the staging tool SHALL create a new `source_pdfs` row and a fresh `processing_status` row, and the previous version's clearance does not carry over to the new version.

### Requirement 2: Extraction gate enforcement

**User Story:** As an operator, I want both the Skill and the staging tool to independently enforce the Extraction_Gate, so that no run is ever extracted from an uncleared PDF.

#### Acceptance Criteria

1. WHEN the Skill is about to begin extraction, the skill SHALL read the `processing_status` row for the registered `pdf_id` resolved from the packet's `drive_file_id` and `file_hash` and proceed only if `risk_decision` is `"non_critical"` or `clearance_by` is populated.
2. IF neither a `non_critical` decision nor a human clearance is recorded for the SourcePDF, THEN the skill SHALL stop, inform the operator that reviewer clearance is required, and produce zero extraction JSON packets.
3. WHEN the staging tool receives an extraction JSON packet via `stage-drafts`, the staging tool SHALL check `processing_status` for the same `drive_file_id` and `file_hash` and reject the packet if neither condition of the Extraction_Gate is met.
4. IF the staging tool rejects an extraction JSON packet due to a failed Extraction_Gate check, THEN the staging tool SHALL return exit code `1` with a message identifying the `drive_file_id` and `file_hash` and explaining the missing clearance, and no rows SHALL be written.

*Cross-reference: Design Property 1 — Extraction gate.*

### Requirement 3: Skill invokes stage-drafts automatically

**User Story:** As an operator, I want the Skill to call `stage-drafts` automatically after producing an extraction JSON packet, so that drafts appear as Pending review in the review app without a manual JSON upload step.

#### Acceptance Criteria

1. WHEN the SourcePDF passes the Extraction_Gate, the skill SHALL produce a versioned extraction JSON packet and immediately call `python staging.py stage-drafts <packet.json> <database.sqlite>`.
2. WHEN the staging tool returns exit code `0` from `stage-drafts`, the skill SHALL report the number of staged rows to the operator.
3. WHEN the staging tool is unavailable or returns a non-zero exit code from `stage-drafts`, the skill SHALL save the completed extraction JSON packet, report the blocker to the operator, and stop without claiming drafts were staged.
4. WHEN `stage-drafts` succeeds, the review app SHALL display the newly staged DraftRuns with status `"Pending review"` immediately.

### Requirement 4: Risk assessment — non-critical tier

**User Story:** As an operator, I want PDFs with no critical or uncertain issues to proceed directly to extraction, so that runs from clean logs reach the review queue without manual intervention.

#### Acceptance Criteria

1. WHEN the Skill produces a risk JSON packet with `decision` equal to `"non_critical"`, the staging tool SHALL record `risk_decision` as `"non_critical"` in `processing_status` and set `status` to `"risk_assessed"`.
2. WHEN a SourcePDF has `risk_decision` equal to `"non_critical"` and no clearance is required, the skill SHALL proceed to extraction for that PDF version without waiting for reviewer input.
3. WHEN issues are confined to the lower measurement table of a PDF, the skill SHALL not classify those issues as critical or uncertain for the purpose of determining the risk tier.

### Requirement 5: Risk assessment — critical and uncertain tiers

**User Story:** As an operator, I want PDFs with critical or uncertain issues to be held before extraction until an authorized reviewer records clearance, so that no run with a data-integrity risk is staged without human review.

#### Acceptance Criteria

1. WHEN the Skill produces a risk JSON packet with `decision` equal to `"critical"` or `"uncertain"`, the staging tool SHALL record the decision in `processing_status` and set `status` to `"held_pending_clearance"`.
2. WHEN any run in a PDF has a critical or uncertain issue, the skill SHALL hold the entire PDF before extraction, not only the affected run.
3. WHILE a SourcePDF has `status` equal to `"held_pending_clearance"` and no clearance is recorded, the skill SHALL not start extraction for that PDF version.
4. WHEN a critical issue is first discovered during draft review (after extraction), the review app SHALL set the affected DraftRun's `review_status` to `"Held"` and record a `hold_reason` referencing the critical issue, and the review app SHALL not add that DraftRun to `growth_runs` or search results.
5. IF a risk JSON packet has `decision` equal to `"uncertain"`, THEN the staging tool SHALL treat it identically to a `"critical"` decision for the purpose of the Extraction_Gate.

### Requirement 6: Reviewer clearance of held PDFs

**User Story:** As a reviewer, I want to record clearance for a held PDF directly in the review app, so that the operator can resume extraction on the same PDF version without handling raw JSON or database commands.

#### Acceptance Criteria

1. WHEN a SourcePDF has `status` equal to `"held_pending_clearance"`, the review app SHALL display the PDF's issues and a prompt for the Reviewer to record clearance.
2. WHEN a Reviewer records clearance, the review app SHALL require the Reviewer to select their name from the reviewer dropdown before the clearance action can proceed.
3. WHEN a Reviewer submits clearance, the review app SHALL record `clearance_by`, `clearance_at`, and a non-empty `clearance_note` in `processing_status` and transition `status` to `"cleared"`.
4. WHEN clearance is recorded for a SourcePDF, the skill SHALL proceed with extraction when the operator resumes it on the same `pdf_id` and `file_hash`.
5. WHEN a Drive file is replaced and a new SourcePDF version is created, the review app SHALL require a fresh risk assessment for the new `file_hash` and SHALL NOT carry over clearance from a previous version.

### Requirement 7: Reviewer identity and confirmation

**User Story:** As a lab administrator, I want every recorded action to identify the reviewing person by name, so that all clearances, corrections, holds, and approvals are auditable.

#### Acceptance Criteria

1. BEFORE any recorded action (clearance, correction, hold, or approval), the review app SHALL require the Reviewer to select a name from the reviewer dropdown.
2. WHEN a Reviewer has selected a name, the review app SHALL display the selected name on the confirmation screen before the action is submitted.
3. IF no reviewer name is selected, THEN the review app SHALL prevent the action from proceeding and display a prompt to select a name.
4. the review app SHALL store reviewer names in the app configuration; reviewer names SHALL NOT be editable from within the app during a review session.

### Requirement 8: Draft review — open source PDF

**User Story:** As a reviewer, I want to open a DraftRun alongside the source PDF at the exact page and measurement-table row, so that I can verify the extracted fields against the original scan.

#### Acceptance Criteria

1. WHEN a Reviewer opens a DraftRun in the review app, the review app SHALL display the extracted fields and a rendered view of the source PDF.
2. WHEN displaying the source PDF, the review app SHALL open it at the page number and measurement-table row recorded in `source_locations_json` for that DraftRun.
3. IF `source_pdfs.storage_path` does not resolve to a readable file, THEN the review app SHALL display the error in the source-PDF viewer panel and allow the Reviewer to continue reviewing the available fields.
4. WHEN multiple source locations are recorded for a DraftRun (run spanning pages), the review app SHALL make all recorded locations accessible to the Reviewer.

### Requirement 9: Draft review — field correction

**User Story:** As a reviewer, I want to correct any field on a DraftRun and have the correction recorded with full provenance, so that the approved record reflects the reviewer's verified interpretation.

#### Acceptance Criteria

1. WHEN a Reviewer edits a field on a DraftRun, the review app SHALL require the Reviewer to supply a reason for the correction before saving.
2. WHEN a correction is saved, the review app SHALL record the old value, new value, reason, and source location reference in the correction record.
3. the review app SHALL preserve `original_json` unmodified; corrections SHALL be stored separately and not overwrite the original extraction.
4. WHEN a Reviewer submits a correction, the review app SHALL require the Reviewer's name to be selected in the reviewer dropdown before the correction is recorded.

### Requirement 10: Draft review — hold

**User Story:** As a reviewer, I want to hold a DraftRun with a written reason, so that runs with unresolved issues stay out of search until the issue is resolved.

#### Acceptance Criteria

1. WHEN a Reviewer holds a DraftRun, the review app SHALL require a non-empty `hold_reason` before the hold can be saved.
2. WHEN a DraftRun is held, the review app SHALL set `review_status` to `"Held"` and record `hold_reason` in `draft_runs`.
3. WHILE a DraftRun has `review_status` equal to `"Held"`, the review app SHALL not include that run in `growth_runs` or in search results.
4. WHEN a Reviewer holds a DraftRun, the review app SHALL make the hold and its reason visible to the operator in the processing status view.
5. WHEN more information becomes available, the review app SHALL allow the Reviewer to reopen a held DraftRun and resume the approval workflow.

*Cross-reference: Design Property 5 — Hold reason required.*

### Requirement 11: Draft approval — preconditions

**User Story:** As a reviewer, I want the app to verify that all required fields are confirmed before I approve a run, so that every GrowthRun in the archive has a verifiable source, a searchable value, and confirmed stoichiometry.

#### Acceptance Criteria

1. WHEN a Reviewer attempts to approve a DraftRun, the review app SHALL verify that at least one `source_locations_json` entry pointing to a valid page and measurement row is present.
2. WHEN a Reviewer attempts to approve a DraftRun, the review app SHALL verify that at least one Lookup_Value (`researcher_name`, `growth_date`, or `jc_number`) is populated.
3. WHEN a Reviewer attempts to approve a DraftRun, the review app SHALL verify that stoichiometry is recorded in `composition_json`.
4. IF any precondition in criteria 1–3 is not met, THEN the review app SHALL prevent approval, identify the unmet precondition, and allow the Reviewer to hold the draft or return to editing.

*Cross-reference: Design Property 6 — Approved run completeness.*

### Requirement 12: Draft approval — atomic transaction

**User Story:** As a reviewer, I want approval to be an all-or-nothing operation, so that the archive never contains a GrowthRun without a matching revision record.

#### Acceptance Criteria

1. WHEN a Reviewer confirms approval, the review app SHALL execute a single SQLite transaction that inserts a row in `growth_runs`, inserts a row in `run_revisions` with `approved_by`, `approved_at`, the approved-values snapshot, and any recorded corrections, and updates `draft_runs.review_status` to `"Approved"`.
2. the review app SHALL display "Saved" only after the approval transaction commits.
3. IF the approval transaction fails, THEN the review app SHALL show the error message, leave the form in an editable state, and leave `growth_runs` and `run_revisions` unchanged.
4. WHEN a Reviewer retries an approval that already committed before the app displayed confirmation, the review app SHALL detect the existing `run_id` and `version` and return the saved revision without inserting a duplicate.

*Cross-reference: Design Properties 2, 9 — Atomic approval; Failed transaction atomicity.*

### Requirement 13: Stale approval protection

**User Story:** As a reviewer, I want the app to detect when a draft or run has changed since I opened it, so that my approval cannot silently overwrite a newer decision or create a duplicate revision.

#### Acceptance Criteria

1. BEFORE writing an approval transaction, the review app SHALL read the current `run_revisions.version` for the run and the current `draft_runs.updated_at` for the draft.
2. IF either value has changed since the Reviewer opened the draft, THEN the review app SHALL reload and display the latest state and require the Reviewer to confirm before proceeding with approval.

*Cross-reference: Design Property 8 — Stale approval safety.*

### Requirement 14: Processing status view

**User Story:** As an operator, I want a processing status view that shows the outcome for every processed PDF, so that I can track the pipeline and act on PDFs that need attention.

#### Acceptance Criteria

1. the review app SHALL provide a processing status view that lists every SourcePDF that has been processed, with its current risk tier, `processing_status.status`, and any hold or failure reason.
2. WHEN a SourcePDF has reached extraction, the review app SHALL display a summary of its DraftRun statuses (e.g. "3 approved · 2 pending · 1 held").
3. WHEN a Reviewer acts on a DraftRun, the review app SHALL update the counts on the processing status view to reflect the new status.
4. WHEN a SourcePDF has `status` equal to `"held_pending_clearance"`, the review app SHALL display the PDF's issues and a clearance prompt to the Reviewer.
5. the review app SHALL display held-pending-clearance PDFs and technical-failure PDFs as visually distinct outcomes; technical failures SHALL include an indication that the failure is retryable.
6. WHEN approved GrowthRuns from a SourcePDF exist, the review app SHALL make those runs searchable even while other DraftRuns from the same PDF remain pending or held.
7. WHEN every SourcePDF that has been processed has a row in `processing_status`, the SQLite database SHALL record an outcome for each one.

### Requirement 15: Search — approved runs only

**User Story:** As a researcher, I want search to return only approved runs, so that I never find a pending or held draft in my search results.

#### Acceptance Criteria

1. the review app SHALL query only `growth_runs` for search results.
2. WHEN a search query is executed, the review app SHALL not return any row from `draft_runs` regardless of its `review_status`.
3. WHEN a GrowthRun has an unresolved critical issue (held DraftRun), the review app SHALL not return that run in search results until an approved GrowthRun row exists.

*Cross-reference: Design Property 7 — Search isolation.*

### Requirement 16: Search — researcher name

**User Story:** As a researcher, I want to search by researcher name alone, so that I can find all runs attributed to a specific person.

#### Acceptance Criteria

1. WHEN a researcher submits a name query, the review app SHALL return all GrowthRuns whose `researcher_name` contains the query string as a substring.
2. the review app SHALL perform researcher-name searches case-insensitively.
3. WHEN a researcher name query is the only input, the review app SHALL return results without requiring any other search field.

### Requirement 17: Search — growth date

**User Story:** As a researcher, I want to search by month or exact date alone, so that I can find all runs from a specific period.

#### Acceptance Criteria

1. WHEN a researcher submits a month query in `YYYY-MM` format, the review app SHALL return all GrowthRuns whose `growth_date` starts with that `YYYY-MM` prefix, matching both month-only and day-precision dates within that month.
2. WHEN a researcher submits an exact date query in `YYYY-MM-DD` format, the review app SHALL return only GrowthRuns whose `growth_date` equals that exact value.
3. WHEN a date or month query is the only input, the review app SHALL return results without requiring any other search field.
4. WHEN displaying a GrowthRun with a month-only `growth_date` (e.g. `2020-01`), the review app SHALL display it without an invented day component.
5. WHEN sorting results that include both month-only and day-precision dates within the same month, the review app SHALL sort month-only entries before day-precision entries.

### Requirement 18: Search — combined name and month

**User Story:** As a researcher, I want to search by both name and month together, so that I can narrow results to a specific person in a specific period.

#### Acceptance Criteria

1. WHEN a researcher supplies both a name query and a month query, the review app SHALL return only GrowthRuns that match both the researcher-name substring condition and the month prefix condition simultaneously.
2. WHEN a researcher supplies both inputs and no GrowthRun matches both, the review app SHALL return an empty result set.

### Requirement 19: Search — JC number and growth process filter

**User Story:** As a researcher, I want to search by JC number and filter by growth process, so that I can find specific experiments or batches.

#### Acceptance Criteria

1. WHEN a researcher searches by JC number, the review app SHALL return all GrowthRuns whose `jc_number` equals the searched value or whose raw written JC contains the searched value as a substring.
2. WHEN multiple GrowthRuns share the same `jc_number`, the review app SHALL return all matching runs and display each run's source PDF filename and measurement-table row so the researcher can distinguish them.
3. WHEN a researcher applies a growth-process filter (CVT, Flux Growth, unclear, or any), the review app SHALL restrict results to GrowthRuns with the matching `growth_process` value; selecting "any" SHALL apply no filter.

### Requirement 20: Search — sort order and source PDF link

**User Story:** As a researcher, I want consistent sort order and a direct link to the source scan, so that I can find and open the original measurement row quickly.

#### Acceptance Criteria

1. WHEN multiple GrowthRuns share the same `growth_date` and have no `jc_number`, the review app SHALL sort those runs alphabetically by `researcher_name`, then by `run_id` when researcher names also match.
2. WHEN a search result is displayed, the review app SHALL show an "Open source PDF" action for each result.
3. WHEN a researcher activates the "Open source PDF" action, the review app SHALL open the SourcePDF at the page number and measurement-table row recorded in `source_locations_json` for that GrowthRun.

### Requirement 21: Staging tool — packet validation

**User Story:** As an operator, I want the staging tool to validate every packet before writing anything to the database, so that malformed or incompatible packets never produce partial records.

#### Acceptance Criteria

1. WHEN the staging tool receives a packet, the staging tool SHALL verify that `schema_version` is present and equal to a supported version; an unsupported version SHALL result in exit code `1` and no database writes.
2. WHEN the staging tool receives a packet, the staging tool SHALL verify that `stage`, `drive_file_id`, `file_hash`, `model`, and `prompt_version` are all present and non-empty strings; a missing or empty key SHALL result in exit code `1`.
3. WHEN the staging tool receives an extraction packet, the staging tool SHALL look up the `drive_file_id` and `file_hash` combination in `source_pdfs`; if no matching row exists, the staging tool SHALL reject the packet with exit code `1` and a message stating that `risk-assess` must complete for that version first.
4. WHEN the staging tool receives a risk JSON packet, the staging tool SHALL verify that `decision` is one of `"non_critical"`, `"critical"`, or `"uncertain"` and that `issues` is an array; an invalid value SHALL result in exit code `1`.
5. WHEN the staging tool receives an extraction JSON packet, the staging tool SHALL verify that each run entry has `draft_id`, `source_locations`, and a `fields` object containing all required keys with valid `status` values; a violation SHALL result in exit code `1`.
6. WHEN the staging tool encounters any validation failure, the staging tool SHALL print a descriptive error message and leave the SQLite database unchanged.

### Requirement 22: Staging tool — idempotent import

**User Story:** As an operator, I want to safely replay a saved packet without creating duplicate records, so that retrying a failed or uncertain import never corrupts the database.

#### Acceptance Criteria

1. WHEN the staging tool receives an extraction JSON packet that is byte-for-byte identical to a previously imported packet, the staging tool SHALL stage zero new rows and exit with code `0`.
2. WHEN the staging tool receives an extraction JSON packet where a run's `draft_id` already exists in `draft_runs` for the same `pdf_id` and `file_hash` with identical JSON content, the staging tool SHALL skip that run without error.

*Cross-reference: Design Property 3 — Idempotent import.*

### Requirement 23: Staging tool — conflict detection

**User Story:** As an operator, I want the staging tool to reject a changed packet for an existing draft, so that I must resolve discrepancies before any record is overwritten.

#### Acceptance Criteria

1. WHEN the staging tool receives an extraction JSON packet where a run's `draft_id` already exists in `draft_runs` for the same `pdf_id` and `file_hash` but with different JSON content, the staging tool SHALL report the conflicting `draft_id` and both JSON payloads, exit with code `1`, and write no rows.
2. WHEN a conflict is reported, the staging tool SHALL roll back any partial writes so that the SQLite database remains unchanged.

*Cross-reference: Design Property 4 — Conflict rejection.*

### Requirement 24: Staging tool — atomic transaction

**User Story:** As an operator, I want every packet import to succeed or fail as a unit, so that the database never ends up in a partially written state.

#### Acceptance Criteria

1. the staging tool SHALL execute the entire import of a packet in a single SQLite transaction.
2. IF any validation check fails or a conflict is detected during import, THEN the staging tool SHALL roll back the transaction and leave the SQLite database unchanged.
3. WHEN a packet imports successfully, the staging tool SHALL print the number of rows staged and exit with code `0`.

### Requirement 25: Test and Archive environments

**User Story:** As an operator, I want separate Test and Archive environments with isolated SQLite databases, so that test approvals never mix with official archive records.

#### Acceptance Criteria

1. the staging tool and the review app SHALL support two environments: Test (using `test.sqlite`) and Archive (using `archive.sqlite`).
2. WHEN the operator resets the Test environment, the staging tool SHALL clear only Test data; source PDFs in Drive and Archive data SHALL remain unaffected.
3. WHEN the operator processes a source PDF in the Archive environment, the review app SHALL require fresh approvals independent of any decisions recorded in the Test environment.
4. WHILE a walkthrough or acceptance run is in progress, the review app SHALL clearly label the active environment (Test or Archive) on every page.

### Requirement 26: Archive backup and restore

**User Story:** As an operator, I want daily backups of the Archive database with a verified restore procedure, so that approved records, review history, and source PDF references can be recovered after data loss.

#### Acceptance Criteria

1. the operator SHALL create a consistent SQLite snapshot of `archive.sqlite` using SQLite's backup mechanism at the end of each day that includes Archive changes and before any database migrations.
2. WHEN creating a backup, the operator SHALL include the review workspace and the exact retained source PDF versions needed to reopen approvals.
3. the operator SHALL record the timestamp of the last successful off-device backup and investigate any failure.
4. the operator SHALL store backups in a restricted backup folder in the lab's shared Drive, separate from the binder folders. *(Pending lab confirmation: backup folder path and naming convention.)*
5. the operator SHALL target losing at most one day of approvals and corrections. *(Pending lab confirmation: recovery time objective.)*
6. the operator SHALL target restoring searchable records, review history, and source PDF links within one working day of reporting the data loss. *(Pending lab confirmation: recovery time objective.)*
7. WHEN performing a restore drill, the operator SHALL restore into a separate Test workspace and verify that approved runs are searchable, review history is present, and source PDF links open the exact PDF versions the reviewers saw.

### Requirement 27: Walkthrough testing

**User Story:** As an operator, I want a structured walkthrough using non-reserved PDFs that covers all missing and unclear information cases, so that the skill, staging tool, and review app can be tuned before the acceptance run.

#### Acceptance Criteria

1. the walkthrough SHALL use PDFs from both Binders 1 and 2 that are not on the reserved acceptance list.
2. the walkthrough SHALL include at least one PDF example covering each of the following cases: missing researcher name, missing growth date with a usable timestamp, missing growth date without a usable timestamp, missing JC number, no usable lookup value, missing stoichiometry, ambiguous stoichiometry, unclear source row or page, and each category of missing optional information (furnace cycle, furnace layout, growth process, timestamp, optional measurement).
3. the walkthrough SHALL include at least one end-to-end run that starts with a source PDF and results in a DraftRun appearing as "Pending review" in the review app without any manual JSON upload.
4. WHEN the walkthrough is complete, the operator SHALL record the results before resetting the Test environment.
5. The specific PDF filenames and Drive IDs used in the walkthrough are not fixed by this requirements document and SHALL be selected by the operator from the existing Drive inventory. *(Pending operator selection.)*

### Requirement 28: Acceptance run

**User Story:** As a lab administrator, I want a formal acceptance run against a reserved set of PDFs whose expected outcomes are recorded independently of the skill's output, so that Iris can sign off with confidence before wider batch processing.

#### Acceptance Criteria

1. the acceptance run SHALL use only PDFs from the reserved acceptance list; those PDFs SHALL NOT have been used in any walkthrough tuning session.
2. BEFORE the acceptance run begins, an authorized Reviewer SHALL record the expected risk tier, expected run count, expected source page and row for each run, expected values for name, date, JC number, and stoichiometry where readable, and expected approval or hold status for each draft — all without relying on the Skill's output.
3. the acceptance checklist SHALL be keyed by filename, Drive ID, and version hash (`file_hash`).
4. WHEN the acceptance run is executed, the operator SHALL run `$stage-log-runs` in the Test environment on each reserved PDF and compare the staging tool's recorded outcomes against the checklist.
5. WHEN a critical or uncertain PDF is encountered during the acceptance run, the review app SHALL show a hold reason, and zero DraftRuns SHALL appear for that PDF before clearance is recorded.
6. WHERE a Reviewer can resolve a hold during the acceptance run, the operator SHALL record clearance and rerun the same PDF version to verify that extraction resumes.
7. WHEN the acceptance run is complete, the review app SHALL show that every reserved PDF has a recorded outcome, every eligible DraftRun appeared in "Pending review" without manual JSON upload, and every required approval or hold was exercised.
8. WHEN Iris signs off on the acceptance-run results, the operator SHALL record the sign-off before beginning wider batch processing in the Archive environment.
