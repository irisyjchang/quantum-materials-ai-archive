# Quantum Materials Lab — Growth Log Archive Design

**Draft for lab review** · Version 0.5 · November 8, 2026

**Scope** · Local MVP for reviewed log runs

## 1. Problem and outcome

A researcher looking for a past log run may have to open several handwritten growth logs and cross-reference a JC number, date, compound, or furnace cycle. A log run is one crystal growth experiment documented in a paper log. One log can contain several log runs. Some older log runs lack a JC number or use a short suffix. The first workflow covers the scanned growth logs.

The MVP succeeds when a researcher can look up a reviewed run by name, date, or JC number and open the original log at the relevant page and row while offline. The MVP demonstrates this with the pilot collection. The shared app should make the full archive the researcher is authorized to access available offline after a complete sync.

**After the MVP, the researcher's job is to take and submit a photo of the paper log.** The archive converts the photo to a PDF, checks that the PDF opens and renders, and extracts the recorded values. Unclear entries go to a designated reviewer. Once reviewed, the log runs become searchable with a link back to the original log PDF.

The MVP tests AI extraction, human review, and search on existing scans. For each run, the AI draft includes the researcher’s name, date, JC number if present, and composition as written, including any recorded ratios or weights. It points to the page and row in the original log and marks anything missing or unclear. A reviewer checks and corrects the draft against the original log.

## 2. Status

- **[Drive inventory](https://drive.google.com/drive/folders/1q7wCJ1IxHwI8ItlhNOxSp9ZoZWkbgrn5).** Folder 1 has 152 prepared PDFs and folder 2 has 203, for 355 files. The archive addresses follow `log-1-###.pdf` and `log-2-###.pdf`. The filename index maps each address to its original file and Drive ID. A file address identifies a scan. A JC number is an optional identifier written on a run.
- **How the paper logs were scanned.** We sorted the logs into two groups. Paper logs that could feed safely through the UW paper scanner were scanned in batches grouped by log binder number. The resulting PDFs were then split into one PDF per page. Paper logs with tape or sticky notes that could catch in the scanner were photographed with Adobe Scan. The 30 repaired Adobe PDFs preserve 35 page images and rendered without the original decoding errors. Some logs contain several runs, and a run may span several pages in the original log.
- **Extraction and storage.** [Run 01](../pilot/runs/chatgpt/pdf-to-json/run01/README.md) is an unvalidated ChatGPT transcription of JC1301–JC1303. A local SQLite walkthrough stages and searches those three rows and demonstrates a reversible correction. These artifacts provide a starting point for the pilot.

## 3. MVP decisions and trade-offs

1. **Reuse the local SQLite walkthrough.** Extend the existing import and search workflow for reviewed log runs. The operator can use local commands for the first demo. Add a web interface when lab users identify a task the local workflow makes difficult.
2. **Use one approved extractor.** Start with the existing ChatGPT workflow if the lab approves it for these scans. Have it return a structured JSON draft with a source reference for each log run. One extractor is sufficient to test the MVP workflow.
3. **Review outside the app.** A lab reviewer checks the packet against the scan in Drive and records their name and decision on the reviewed version. Code checks the packet and imports it. This keeps the human gate without building a review queue or approval service.
4. **Preserve the source and corrections.** Keep the original draft alongside the reviewed packet. If a value changes, review the revised packet before importing it. An identical retry can reuse the existing review decision.

## 4. Workflow and ownership

**Pilot intake for paper logs that cannot feed through the UW scanner.** Take a regular phone photo that shows the whole log, including tape, sticky notes, and writing in the margins. Attach it in ChatGPT with its log binder number. The assistant converts the photo to PDF, checks that the PDF opens and that the visible writing and notes are preserved, then uploads it to the matching Drive folder with the next available log number. If the photo is blurry or cropped, ask for a retake. This trial tests capture, PDF verification, and filing before those steps are built into the app.

1. **Preparer selects a scan.** Record the Drive file ID, page, and worksheet row. Check the page is readable and account for every populated row.
2. **AI extracts the recorded values.** The preparer submits the scan to the approved extractor. The draft preserves uncertain text and links each log run to the original log.
3. **Lab reviewer checks the draft.** Confirm or correct values using the original log. Record the reviewer, date, and reviewed version. Set aside rows with unresolved critical fields.
4. **Operator imports and searches.** Validate the reviewed packet, import it into SQLite, and retrieve the log run by name, date, or JC. Confirm the result points to the relevant page and row in the original log.

One person can prepare and operate the pilot. The lab designates who verifies the science.

## 5. Log run fields and scientific boundaries

**Confirm the basic fields with the lab before starting the pilot.** The notes identify the recorded date, JC number when present, and stoichiometry, including written ratios, as the starting set. Researcher name is proposed for search. Capture measurements when they are recorded, and use start or end timestamps as supporting evidence when the date is missing. Ask the lab to confirm which missing or ambiguous values block import and which can remain unresolved.

| Field group | Capture | Examples that need a closer look |
| --- | --- | --- |
| Identity | Researcher name, written JC, and confirmed full JC where known | A suffix could match more than one run, or JC order conflicts with date order |
| Date | Day or month precision as written. Keep timestamp evidence if used to infer a date | The header is blank and timestamps conflict or imply different months |
| Composition | Formula, ratios with component order, weights and units, and separate calculated and measured values. Capture handwritten `x` or doping notation when present. | A digit is overwritten, an element symbol is unclear, or the ratio basis is unknown |
| Furnace program | Optional source note for the written program or a pointer to the graph | Two temperatures lack labels, graph axes are unclear, or the timing of a step is ambiguous |
| Technique and layout | Optional source note for the written technique, transport agent, or layout drawing | The technique is inferred from clues or the layout is unclear |

Search by name, date, and JC as written. Display the raw composition with the search result. Record furnace, technique, layout, measurements, and timestamps as source notes when present. Detailed furnace parsing and automated technique classification can wait. Leave load outside the required pilot fields. Preserve the difference between an inspected blank, an unreadable entry, an ambiguous reading, an inferred value, and a value omitted by the extractor. A known partial JC remains searchable as written. For log runs with the same date and no confirmed JC, use researcher name and stable log run ID to break ties.

**Optional `x` column and calculated `x`.** Capture the handwritten `x` when present. A blank `x` column is valid and does not block import. When the log gives reagent masses, convert grams to moles using the relevant molar masses. For a compound reagent, use its formula to account for how many atoms of the relevant element it contributes. Then calculate `x` from the molar ratio for the site or composition the lab specifies. For example, if `x` is the fraction of a site occupied by the dopant, divide the dopant moles assigned to that site by the total moles assigned to it. On that basis, “5% doped” means `x = 0.05`. Keep the calculated value separate from any handwritten `x`, along with the masses, units, molar mass reference, and calculation. If the basis is unclear or the recipe includes excess flux, flag the calculation for review before using it.

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

Start once the lab confirms the basic fields and review tiers. Use Run 01 and a few representative pages. A proposed first set is 5–10 pages, including a log with several runs and a log with a partial or missing JC number. Have a lab reviewer establish the expected rows and values.

Compare the extractor's draft with the values and rows the lab reviewer confirms from the scan. Track missed rows, incorrect critical fields, and the time spent reviewing and correcting the draft. Reserve a few pages to check the result after the prompt is fixed. If extraction fails or the source cannot support a critical value, keep that log run out of the import until the issue is resolved.

The MVP is ready for a lab walkthrough when a reviewer can:

- Approve a packet for the sample log runs and import it successfully.
- Find a known run by name, date, or JC and open the original log at the relevant page and row.
- Keep a missing or partial JC exactly as recorded.
- Hold a row with an unresolved critical issue and import a reviewed row with an optional detail marked unresolved.
- Retry the same import without duplicating database entries and see a clear error for an invalid or conflicting packet.
- Disconnect the laptop and reopen the local tools. Search the pilot log runs and verify that every original log PDF in the pilot collection opens without a connection.

## 8. Photo capture after the MVP

Add a phone-friendly capture screen where a researcher takes and submits a photo. If the photo is blurry or cuts off part of the log, ask for a retake. Otherwise, convert the photo to PDF and render every page to check that the conversion worked. Hold a failed PDF out of the archive and retry from the captured image. Use the verified PDF as the archive copy and make it available to the reviewer alongside the extracted values. The researcher enters additional information only when a reviewer needs their help resolving something the photo cannot establish.

**Offline archive access.** Sync the full authorized archive to the device, including the searchable log runs and their original logs. Show when the download is complete and when it last synced. Keep the last complete copy usable if a refresh is interrupted. A researcher can still browse and open the downloaded archive while new uploads and updates wait for a connection.

**Offline photo capture.** Save the photo on the device when the connection drops and show it as pending. Upload and start extraction after reconnecting. Keep the pending photo until the archive confirms the PDF was saved and passed its rendering check. Use the same submission ID for retries to avoid duplicates. Test by taking a photo offline, reopening the capture screen, and reconnecting.

Before rolling this out, confirm who handles exceptions and which fields need review on every log run. Test on actual phone photos, including pages with several runs and notes in the margins. Measure both the time researchers spend submitting a log and the time reviewers spend checking it. Use those results to decide which fields can move to spot checks.

Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later.
