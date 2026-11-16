---
name: stage-log-runs
description: Assess crystal-growth log PDFs, extract source-linked run drafts from eligible scans, and stage them through the local staging tool for human review in the Quantum Materials Lab archive.
---

# Stage log runs

Work on the PDF or batch the operator specifies, in the selected Test or Archive workspace. Resolve the source from the local path or Drive inventory, record its source ID, and hash the exact bytes inspected. Keep the original PDF in its binder folder. If a local copy is needed, retain it in approved storage so the reviewer can open the same version.

Follow the [review and extraction rules](../../../DESIGN-MVP.md#5-log-run-review-and-extraction), the [MVP JSON handoff](../../../DESIGN-MVP.md#json-handoff), and the [staging tool interface](../../../.kiro/specs/local-growth-log-mvp/design.md#staging-tool-cli). Use the implemented MVP staging tool in the selected workspace. If it is unavailable, save any completed assessment, report the blocker, and stop before extracting without a recorded decision or claiming drafts were staged. Keep source files and packets out of Git.

## Assess and route the PDF

1. Inspect the measurement table on all relevant pages. Use the upper Calculated table when present and ignore the lower table. Read headers, margins, and notes for context. Identify the runs and their page and row locations. If a run spans pages, retain all relevant locations.
2. Check whether every run can be tied to a source location, has at least one usable lookup value (researcher name, date or month, or JC identifier), and has interpretable stoichiometry. Treat an issue as critical when it could attach values to the wrong run or change the meaning of the stoichiometry. A missing JC can be acceptable when another lookup value is available.
3. Save a versioned risk packet. Use `non_critical` when extraction can proceed, `critical` when any run has a critical issue, and `uncertain` when the PDF cannot be reliably assessed. Record each issue and its source location when known. Call the staging tool's `risk-assess` command to record the assessment result.
4. Before extracting, read the stored assessment result for this exact `drive_file_id` and `file_hash`. Proceed only with a recorded `non_critical` decision or clearance recorded by an authorized reviewer. For `critical` or `uncertain` without clearance, leave the whole PDF held in the app and report the issue, its location, and what would resolve it. On resume, check the stored decision before retrying; preserve any existing reviewer clearance. A replacement scan needs its own assessment.

## Extract and stage drafts

1. Produce a versioned extraction packet with one entry per run. Include a packet-local `draft_id` and the required `source_locations`. Use 1-based PDF pages and count measurement-table rows from 1, skipping the header. Keep duplicate or partial JC values as written.
2. Preserve original formula, ratios, quantities, units, and basis where recorded. Keep any normalized or derived value separate from the transcription and show its evidence or calculation. Distinguish absent, illegible, ambiguous, inferred, and derived values with the packet's field statuses. Carry forward optional uncertainty and flag any critical issue discovered during extraction.
3. Validate the packet against the MVP JSON handoff, including source, model, and prompt version metadata. Save the packet in the selected workspace and call the staging tool's `stage-drafts` command. Use the staging tool result to verify staging. Never write directly to SQLite or substitute a manual JSON handoff for a successful import.
4. Report the outcome for each PDF: held before extraction (with reason), drafts staged for review (with count), already staged, or technical failure (with the error). Newly staged drafts appear as Pending review in the app. Flag any affected run that needs a hold. Only an authorized human reviewer can resolve critical issues, verify the source location, lookup value, and stoichiometry, and approve a run for search.

Example invocation: `$stage-log-runs Assess <PDF path or Drive reference> in Test and stage any eligible drafts for review.`
