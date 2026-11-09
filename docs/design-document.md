# Quantum Materials Lab — Growth Log Archive Design

**Draft for lab review** · Version 0.5 · November 8, 2026

**Scope** · Local MVP for reviewed growth records

## 1. Problem and outcome

A researcher looking for a past crystal growth run may have to open several handwritten worksheets and cross-reference a JC number, date, compound, or furnace cycle. Some sheets contain several runs. Some older records lack a JC number or use a short suffix. The first workflow covers the scanned growth sheets.

The MVP succeeds when a researcher can look up a reviewed run by name, date, or JC number and open the original log at the relevant page and row while offline. The MVP demonstrates this with the pilot collection. The shared app should make the full archive the researcher is authorized to access available offline after a complete sync.

**After the MVP, the researcher's job is to take and submit a photo of the paper log.** The archive should save the photo, check that the page is readable, extract the recorded values, and send unclear entries to a designated reviewer. Once reviewed, the records become searchable with a link back to the photo.

The MVP tests AI extraction, human review, and search on existing scans. The AI reads values such as the date, JC number, and composition from the log and puts them into a record for review. A reviewer checks those values against the original log and corrects them where the handwriting is clear.

## 2. Current evidence

- **Drive inventory.** Folder 1 has 152 prepared PDFs and folder 2 has 203, for 355 files. The archive addresses follow `log-1-###.pdf` and `log-2-###.pdf`. The filename index maps each address to its original file and Drive ID. A file address identifies a scan. A JC number is an optional identifier written on a run.
- **Scan quality.** The UW batches were split into individual pages. Thirty repaired Adobe PDFs preserve 35 page images. The repaired copies rendered without the original decoding errors and require image-based extraction. Some sheets hold several runs, and a run may span several pages in the original log.
- **Extraction and storage.** [Run 01](../pilot/runs/chatgpt/pdf-to-json/run01/README.md) is an unvalidated ChatGPT transcription of JC1301–JC1303. A local SQLite walkthrough stages and searches those three rows and demonstrates a reversible correction. These artifacts provide a starting point for the pilot.

## 3. MVP decisions and trade-offs

1. **Reuse the local SQLite walkthrough.** Extend the existing import and search workflow for reviewed records. The operator can use local commands for the first demo. Add a web interface when lab users identify a task the local workflow makes difficult.
2. **Use one approved extractor.** Start with the existing ChatGPT workflow if the lab approves it for these scans. Have it return a structured JSON draft with a source reference for each record. One extractor is sufficient to test the MVP workflow.
3. **Review outside the app.** A lab reviewer checks the packet against the scan in Drive and records their name and decision on the reviewed version. Code checks the packet and imports it. This keeps the human gate without building a review queue or approval service.
4. **Preserve the source and corrections.** Keep the original draft alongside the reviewed packet. If a value changes, review the revised packet before importing it. An identical retry can reuse the existing review decision.

## 4. Workflow and ownership

1. **Preparer selects a scan.** Record the Drive file ID, page, and worksheet row. Check the page is readable and account for every populated row.
2. **AI extracts the recorded values.** The preparer submits the scan to the approved extractor. The draft preserves uncertain text and links each record to its source.
3. **Lab reviewer checks the draft.** Confirm or correct values using the original log. Record the reviewer, date, and reviewed version. Set aside rows with unresolved critical fields.
4. **Operator imports and searches.** Validate the reviewed packet, import it into SQLite, and retrieve the record by name, date, or JC. Confirm the result points to the relevant page and row in the original log.

One person can prepare and operate the pilot. The lab designates who verifies the science.

## 5. Record contract and scientific boundaries

| Record area | Capture | Examples that need a closer look |
| --- | --- | --- |
| Identity | Researcher name, written JC, and confirmed full JC where known | A suffix could match more than one run, or JC order conflicts with date order |
| Date | Day or month precision as written. Keep timestamp evidence if used to infer a date | The header is blank and timestamps conflict or imply different months |
| Composition | Formula, ratios with component order, raw `x` or doping notation, weights and units, and separate calculated and measured values | A digit is overwritten, an element symbol is unclear, or the ratio basis or substitution site is unknown |
| Furnace program | Optional source note for the written program or a pointer to the graph | Two temperatures lack labels, graph axes are unclear, or the timing of a step is ambiguous |
| Technique and layout | Optional source note for the written technique, transport agent, or layout drawing | The technique is inferred from clues or the layout is unclear |

Search by name, date, and JC as written. Display the raw composition with the search result. Record furnace, technique, layout, measurements, and timestamps as source notes when present. Detailed furnace parsing and automated technique classification can wait. Leave load outside the required pilot fields. Preserve the difference between an inspected blank, an unreadable entry, an ambiguous reading, an inferred value, and a value omitted by the extractor. A known partial JC remains searchable as written. For records with the same date and no confirmed JC, use researcher name and stable record ID to break ties.

For derived values, store the original text, inputs, units, reference, and calculation. A note such as “5% doped” supports `x = 0.05` only when the lab confirms that `x` represents that site's fraction. A transport agent and labeled simultaneous furnace zones can support CVT. A high charge ratio, cooling program, and terminal decant can support flux growth. Record the evidence and route ambiguous cases to a researcher.

### Risk tiers for human review

- **Critical · Hold the record.** Use this tier when an unresolved issue could attach the data to the wrong run or change the scientific meaning of a core field. Examples include an uncertain source row, a conflicting JC number, or an ambiguous compound, ratio, or unit. A reviewer must resolve the issue before the record enters the searchable archive. A JC number that is visibly absent is valid if the source identifies the run.
- **Non-critical · Keep the uncertainty visible.** Use this tier for optional details that can remain unknown without changing the reviewed core record, such as a missing layout note or an unclear optional timestamp. A reviewer can accept the record with that field marked unresolved. If a timestamp is the only evidence for a date the record depends on, review it as a critical issue.

These are proposed rules for lab review. Every MVP record receives human review. The tier determines whether an unresolved issue blocks import.

## 6. Local storage

Keep the PDFs in approved Drive storage. The reviewed JSON packet carries a stable record ID, source file/page/row, written values, any confirmed normalized values, and review evidence. SQLite stores the searchable fields and source reference. A JC number may be missing or partial, so use the internal record ID as the key.

**Offline use in the MVP.** Before disconnecting, put the SQLite database, the local search tools, and every original log PDF in the pilot collection on the laptop. Store a local file reference alongside the Drive reference so search results can open the source without a connection. The operator can also import a reviewed packet already on the laptop. Drive retrieval and cloud extraction wait until the connection returns.

Import a batch in one transaction. A malformed packet should leave the database unchanged. An identical reimport should create zero new rows. A changed packet for an existing record should surface a conflict for the operator. Keep scans, private links, imported research data, and database files out of Git.

## 7. Pilot and acceptance checks

Start with Run 01 and a few representative pages. A proposed first set is 5–10 pages, including a sheet with several runs and a sheet with a partial or missing JC number. Have a lab reviewer establish the expected rows and values.

Compare the extractor's draft with the values and rows the lab reviewer confirms from the scan. Track missed rows, incorrect critical fields, and the time spent reviewing and correcting the draft. Reserve a few pages to check the result after the prompt is fixed. If extraction fails or the source cannot support a critical value, keep that record out of the import until the issue is resolved.

The MVP is ready for a lab walkthrough when a reviewer can:

- Approve a packet for the sample records and import it successfully.
- Find a known run by name, date, or JC and open the original log at the relevant page and row.
- Keep a missing or partial JC exactly as recorded.
- Hold a row with an unresolved critical issue and import a reviewed row with an optional detail marked unresolved.
- Retry the same import without duplicating records and see a clear error for an invalid or conflicting packet.
- Disconnect the laptop and reopen the local tools. Search the pilot records and verify that every original log PDF in the pilot collection opens without a connection.

## 8. Photo capture after the MVP

Add a phone-friendly capture screen where a researcher takes and submits a photo. If the photo is blurry or cuts off part of the sheet, ask for a retake. Otherwise, preserve the original, extract the recorded values into the same format tested in the MVP, and make the scan available to the reviewer. The researcher enters additional information only when a reviewer needs their help resolving something the photo cannot establish.

**Offline archive access.** Sync the full authorized archive to the device, including the searchable records and their source files. Show when the download is complete and when it last synced. Keep the last complete copy usable if a refresh is interrupted. A researcher can still browse and open the downloaded archive while new uploads and updates wait for a connection.

**Offline photo capture.** Save the photo on the device when the connection drops and show it as pending. Upload and start extraction after reconnecting. Keep the pending copy until the server confirms receipt, and use the same submission ID for retries to avoid duplicate records. Test by taking a photo offline, reopening the capture screen, and reconnecting.

Before rolling this out, confirm who handles exceptions and which fields need review on every record. Test on actual phone photos, including pages with several runs and notes in the margins. Measure both the time researchers spend submitting a log and the time reviewers spend checking it. Use those results to decide which fields can move to spot checks.

Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later.
