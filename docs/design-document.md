# Quantum Materials Lab — Growth Log Archive Design

**Draft for lab review** · Version 0.5 · November 8, 2026

**Scope** · Local MVP for reviewed growth records

## 1. Problem and outcome

A researcher looking for a past crystal growth run may have to open several handwritten worksheets and cross-reference a JC number, date, compound, or furnace cycle. Some sheets contain several runs. Some older records lack a JC number or use a short suffix. Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later. The first workflow covers the scanned growth sheets.

The MVP succeeds when a researcher can look up a reviewed run by name, date, or JC number and trace it back to the exact scan page and row.

**The first architecture question** is whether one approved extractor saves time after review. Manual entry can support the full workflow on its own.

## 2. Current evidence

- **Drive inventory.** Folder 1 has 152 prepared PDFs and folder 2 has 203, for 355 files. The archive addresses follow `log-1-###.pdf` and `log-2-###.pdf`. The filename index maps each address to its original file and Drive ID. A file address identifies a scan. A JC number is an optional identifier written on a run.
- **Scan quality.** The UW batches were split into individual pages. Thirty repaired Adobe PDFs preserve 35 page images. The repaired copies rendered without the original decoding errors and require image-based extraction. Some sheets hold several runs, and a run may use several source pages.
- **Extraction and storage.** [Run 01](../pilot/runs/chatgpt/pdf-to-json/run01/README.md) is an unvalidated ChatGPT transcription of JC1301–JC1303. A local SQLite walkthrough stages and searches those three rows and demonstrates a reversible correction. These artifacts provide a starting point for the pilot.
- **Open scientific questions.** The [researcher questions](../researcher-questions/README.md) cover overwritten values, partial identifiers, composition notation, and units. The lab needs to confirm the conventions before the archive normalizes those fields.

## 3. MVP decisions and trade-offs

1. **Reuse the local SQLite walkthrough.** Extend the existing import and search workflow for reviewed records. The operator can use local commands for the first demo. Add a web interface when lab users identify a task the local workflow makes difficult.
2. **Use one record format for manual and AI drafts.** Start with manual entry and optionally test the existing ChatGPT workflow if the lab approves it. Both routes produce the same JSON packet. A single tool is enough to test whether extraction saves time.
3. **Review outside the app.** A lab reviewer checks the packet against the scan in Drive and records their name and decision on the reviewed version. Code checks the packet and imports it. This keeps the human gate without building a review queue or approval service.
4. **Preserve the source and corrections.** Keep the original draft alongside the reviewed packet. If a value changes, review the revised packet before importing it. An identical retry can reuse the existing review decision.

## 4. Workflow and ownership

1. **Preparer selects a scan.** Record the Drive file ID, page, and worksheet row. Check the page is readable and account for every populated row.
2. **Preparer creates a draft.** Enter fields manually or use the approved extractor. Preserve uncertain text and link each record to its source.
3. **Lab reviewer checks the draft.** Confirm or correct values using the original page. Record the reviewer, date, and reviewed version. Set aside rows with unresolved critical fields.
4. **Operator imports and searches.** Validate the reviewed packet, import it into SQLite, and retrieve the record by name, date, or JC. Confirm the result points to the source page and row.

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

## 6. Local storage

Keep the PDFs in approved Drive storage. The reviewed JSON packet carries a stable record ID, source file/page/row, written values, any confirmed normalized values, and review evidence. SQLite stores the searchable fields and source reference. A JC number may be missing or partial, so use the internal record ID as the key.

Import a batch in one transaction. A malformed packet should leave the database unchanged. An identical reimport should create zero new rows. A changed packet for an existing record should surface a conflict for the operator. Keep scans, private links, imported research data, and database files out of Git.

## 7. Pilot and acceptance checks

Start with Run 01 and a few representative pages. A proposed first set is 5–10 pages, including a sheet with several runs and a sheet with a partial or missing JC number. Have a lab reviewer establish the expected rows and values.

If testing an extractor, run manual entry and the extractor on the same pages. Track missed rows, wrong critical values, and total time including correction. Reserve a few pages to check the result after the prompt is fixed. Use AI for drafting only if the initial results justify the review effort. An extractor failure does not block the manual workflow.

The MVP is ready for a lab walkthrough when a reviewer can:

- Approve a packet for the sample records and import it successfully.
- Find a known run by name, date, or JC and open its source page and row.
- Keep a missing or partial JC exactly as recorded.
- Retry the same import without duplicating records and see a clear error for an invalid or conflicting packet.

## 8. Decisions after the MVP

Confirm the required fields, notation rules, and designated reviewer with the lab before expanding the sample. A second extractor is a follow-up experiment if the first exposes a recurring gap worth testing. A web interface, shared hosting, a review queue, CSV export, full archive ingestion, and Dropbox or Slack integration can each be considered once the local workflow has been demonstrated.
