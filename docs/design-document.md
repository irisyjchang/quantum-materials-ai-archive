# Quantum Materials Lab — Growth Log Archive Design

**Draft for lab review** · Version 0.5 · November 8, 2026

**Scope** · Pilot app for photo upload, review, and offline lookup

## 1. Problem and outcome

A researcher looking for a past log run may have to open several handwritten growth logs and cross-reference a JC number, date, compound, or furnace cycle. A log run is one crystal growth experiment documented in a paper log. One log can contain several log runs. Some older log runs lack a JC number or use a short suffix.

The MVP succeeds when a researcher can look up a reviewed run by name, date, or JC number and open the original log at the relevant page and row while offline. The MVP demonstrates this with the pilot collection. The shared app should make the full archive the researcher is authorized to access available offline after a complete sync.

**In the pilot, the researcher takes a photo of a paper log and uploads it in the app.** The app handles PDF conversion, file checks, and tracking the submission through extraction and review. Once approved, the log runs become searchable with a link back to the original log PDF.

The MVP tests photo upload, AI extraction, human review, and search. For each run, the AI draft includes the researcher’s name, date, JC number if present, and composition as written, including any recorded ratios or weights. It points to the page and row in the original log and marks anything missing or unclear. A reviewer checks and corrects the draft against the original log.

## 2. Status

- **[Drive inventory](https://drive.google.com/drive/folders/1q7wCJ1IxHwI8ItlhNOxSp9ZoZWkbgrn5).** Folder 1 has 152 prepared PDFs and folder 2 has 203, for 355 files. The archive addresses follow `log-1-###.pdf` and `log-2-###.pdf`. The filename index maps each address to its original file and Drive ID. A file address identifies a scan. A JC number is an optional identifier written on a run.
- **How the paper logs were scanned.** We sorted the logs into two groups. Paper logs that could feed safely through the UW paper scanner were scanned in batches grouped by log binder number. The resulting PDFs were then split into one PDF per page. Paper logs with tape or sticky notes that could catch in the scanner were photographed with Adobe Scan. The 30 repaired Adobe PDFs preserve 35 page images and rendered without the original decoding errors. Some logs contain several runs, and a run may span several pages in the original log.
- **Extraction and storage.** [Run 01](../pilot/runs/chatgpt/pdf-to-json/run01/README.md) is an unvalidated ChatGPT transcription of JC1301–JC1303. A local SQLite walkthrough stages and searches those three rows and demonstrates a reversible correction. These artifacts provide a starting point for the pilot.

## 3. MVP decisions and trade-offs

1. **Build a small app around the existing SQLite workflow.** The pilot needs a phone-friendly photo upload, submission status, a review view, and search. Reuse the local import and search prototype for reviewed log runs.
2. **Compare three approved models in the MVP pilot.** Run the same logs independently through three models, using the same instructions and JSON format. Comparing drafts can expose disagreements and missed rows, but it adds processing time and work to align the outputs. The original log is the reference for resolving disagreements and checking values all three models agree on.
3. **Keep human review in the workflow.** A designated reviewer checks the draft against the original log in the app and records their decision. The app validates and imports the reviewed values into SQLite.
4. **Preserve the source and corrections.** Keep the original draft alongside the reviewed packet. If a value changes, review the revised packet before importing it. An identical retry can reuse the existing review decision.

**UW Purple for the pilot.** Run the extraction tests in Purple ONEchat. UW lists GPT-6 Sol, Claude Sonnet 5, and Grok 4.6 in Purple. Confirm the model versions and scan upload support before the pilot. Purple access is provided at no additional cost with UW sign-in, subject to a usage allowance. Purple currently provides no API keys, so an operator takes pending PDFs from the app, runs the models in the browser, and returns the JSON drafts to the app. The researcher who uploaded the log can track its status in the app. [UW Purple release notes](https://uwconnect.uw.edu/it?id=kb_article_view&sysparm_article=KB0037881) · [UW Purple FAQ](https://uwconnect.uw.edu/it?id=kb_article_view&sysparm_article=KB0035982)

## 4. Workflow and ownership

1. **Researcher uploads a photo in the app.** Take a photo showing the entire paper log, including any sticky notes and writing in the margins. The app saves the submission, converts it to PDF, and checks that every page renders. If the photo is unreadable or cropped, ask for a retake. Keep the photo available until the PDF has passed its checks and been saved.
2. **Operator runs the three models in Purple.** Give each model the same PDF, instructions, and expected page and row list without the answers. Return the three JSON drafts to the app with their model names and versions. The app compares them by page and row and flags missing runs and conflicting values.
3. **Lab reviewer checks the drafts in the app.** Confirm or correct values against the original log PDF. Save the reviewer, date, and reviewed version. Hold any log run with an unresolved critical issue.
4. **App imports the reviewed log runs.** Validate and save them to SQLite. Researchers can search by name, date, or JC and open the original log at the relevant page and row.

One person can prepare and operate the pilot. The lab designates who verifies the science.

## 5. Log run fields and scientific boundaries

**Basic variables.** The lab confirmed the recorded date, JC number when present, and stoichiometry, including written ratios, before the pilot. Researcher name is proposed for search. Capture measurements when they are recorded, and use start or end timestamps as supporting evidence when the date is missing. Ask the lab to confirm which missing or ambiguous values block import and which can remain unresolved.

| Field group | Capture | Critical |
| --- | --- | --- |
| Identity | Researcher name, written JC, and confirmed full JC where known | A suffix could match more than one run, or JC order conflicts with date order |
| Date | Day or month precision as written. Keep timestamp evidence if used to infer a date | The header is blank and timestamps conflict or imply different months |
| Composition | Formula, ratios with component order, weights and units, and separate calculated and measured values. | An overwritten digit, unclear element symbol, or unknown ratio basis changes how the stoichiometry could be read |
| Furnace program | Optional source note for the written program or a pointer to the graph | — |
| Technique and layout | Optional source note for the written technique, transport agent, or layout drawing | — |

Search by name, date, and JC as written. Display the raw composition with the search result. Record furnace, technique, layout, measurements, and timestamps as source notes when present. Detailed furnace parsing and automated technique classification can wait. Leave load outside the required pilot fields. Preserve the difference between an inspected blank, an unreadable entry, an ambiguous reading, an inferred value, and a value omitted by the extractor. A known partial JC remains searchable as written. For log runs with the same date and no confirmed JC, use researcher name and stable log run ID to break ties.

A transport agent and labeled simultaneous furnace zones can support CVT. A high charge ratio, cooling program, and terminal decant can support flux growth. Record the evidence and route ambiguous cases to a researcher.

### Risk tiers for human review

- **Critical · Hold the log run.** Use this tier when an unresolved issue could attach the data to the wrong run or change the scientific meaning of a core field. Examples include an uncertain source row, a conflicting JC number, or an ambiguous compound, ratio, or unit. A reviewer must resolve the issue before the log run enters the searchable archive. A JC number that is visibly absent is valid if the source identifies the run.
- **Non-critical · Keep the uncertainty visible.** Use this tier for optional details that can remain unknown without changing the reviewed values for that log run, such as a missing layout note or an unclear optional timestamp. A reviewer can accept the log run with that field marked unresolved. If a timestamp is the only evidence for a date the log run depends on, review it as a critical issue.

These tiers are proposed for the lab to confirm using real logs before the pilot. Review a missing JC number, an ambiguous composition or unit, and a missing optional measurement together. Record which cases block import and use those decisions in the pilot's review checklist. Every log run in the MVP receives human review.

## 6. Local storage

Keep the PDFs in approved Drive storage. The reviewed JSON packet carries a stable log run ID, source file/page/row, written values, any confirmed normalized values, and review evidence. SQLite stores the searchable fields and source reference. A JC number may be missing or partial, so use the internal log run ID as the key.

**Offline use in the MVP.** Before disconnecting, put the SQLite database, the local search tools, and every original log PDF in the pilot collection on the laptop. Store a local file reference alongside the Drive reference so search results can open the source without a connection. The operator can also import a reviewed packet already on the laptop. Drive retrieval and cloud extraction wait until the connection returns.

Import a batch in one transaction. A malformed packet should leave the database unchanged. An identical reimport should create zero new rows. A changed packet for an existing log run should surface a conflict for the operator. Keep scans, private links, imported research data, and database files out of Git.

## 7. Pilot and acceptance checks

Start once the lab confirms the review tiers. Use Run 01 as a baseline and have researchers photograph and upload a proposed set of 5–10 representative pages in the app. Include a log with several runs and a log with a partial or missing JC number. Have a lab reviewer establish the expected rows and values.

Compare each extractor's draft with the values and rows the lab reviewer confirms from the original log. Track missed rows, incorrect critical fields, and the time spent preparing, comparing, and reviewing the drafts. On the same logs, check which additional errors the three-tool comparison flags compared with reviewing one draft. Reserve a few pages to check the result after the instructions are fixed. If extraction fails or the original log cannot support a critical value, keep that log run out of the import until the issue is resolved.

The MVP is ready for a lab walkthrough when the team can:

- Take a phone photo and upload it in the app. Verify that the app saves a readable PDF, shows the submission status, and asks for a retake when needed.
- Return the three drafts from Purple, review the flagged values, and verify that approval makes the log runs searchable without a separate import by the researcher.
- Find a known run by name, date, or JC and open the original log at the relevant page and row.
- Keep a missing or partial JC exactly as recorded.
- Hold a row with an unresolved critical issue and import a reviewed row with an optional detail marked unresolved.
- Retry the same import without duplicating database entries and see a clear error for an invalid or conflicting packet.
- Disconnect the laptop and reopen the local tools. Search the pilot log runs and verify that every original log PDF in the pilot collection opens without a connection.

## 8. After the MVP

**Automatic extraction.** Once the pilot identifies which model setup works on the logs, evaluate an approved service with API access so the app can start extraction without the operator transferring files through the browser. Keep the same review and import checks.

**Offline archive access.** Sync the full authorized archive to the device, including the searchable log runs and their original logs. Show when the download is complete and when it last synced. Keep the last complete copy usable if a refresh is interrupted. A researcher can still browse and open the downloaded archive while new uploads and updates wait for a connection.

**Offline photo capture.** Save the photo on the device when the connection drops and show it as pending. Upload and start extraction after reconnecting. Keep the pending photo until the archive confirms the PDF was saved and passed its rendering check. Use the same submission ID for retries to avoid duplicates. Test by taking a photo offline, reopening the capture screen, and reconnecting.

Before rolling this out, confirm who handles exceptions and which fields need review on every log run. Test on actual phone photos, including pages with several runs and notes in the margins. Measure both the time researchers spend submitting a log and the time reviewers spend checking it. Use those results to decide which fields can move to spot checks.

Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later.
