# Researcher Photo Upload Pilot Design

This pilot builds on the archive workflow described in the [MVP design](../DESIGN.md).

**Researcher photo-upload pilot.** A submission contains one growth log and can include one or more page photos. Let the researcher preview and reorder pages and retake an individual blurry or cropped page. Confirm that the full log is readable before sending it to extraction. Convert the ordered pages to one PDF, verify that each page renders, and show submission status. If an upload is interrupted, retry with the same submission ID so the archive creates one PDF for that submission.

**Reuse the processing workflow.** Once an uploaded photo becomes a PDF, send it through the same risk assessment, extraction, human review, and import steps used for the existing Drive logs.

**Shared review.** Reuse the MVP review workflow and reviewer accounts for pilot submissions.

**Pilot hosting decision.** Before inviting pilot participants, choose where the shared app will run long term and confirm who will own the account, cover hosting costs, and maintain backups. Verify that the host provides persistent storage for SQLite and the review workspace. If the pilot uses a different host from the MVP, restore the database, review history, and source references there and verify that reviewers can sign in and open the linked PDFs.

- Ask the lab lead whether the lab already has a server or UW cloud account. If so, request one small instance with persistent storage for SQLite and a place to keep backups. Otherwise, ask UW-IT about a hosted server or a research AWS account and confirm who will own the account and pay for usage. [UW hosting options](https://www.washington.edu/docs/web-at-uw/getting-started/web-hosting-options/) · [UW AWS request process](https://uwconnect.uw.edu/it?id=kb_article_view&sysparm_article=KB0036595)
- If the lab is comfortable with external hosting, consider a paid Render web service with a persistent disk so the SQLite database survives deploys and restarts. [Render persistent disks](https://render.com/docs/disks)

Before rolling out photo uploads, confirm who handles exceptions. Test with actual phone photos. Include a multi-page log with several runs and margin notes, a retake of one page, and an interrupted upload. Verify the saved PDF preserves page order and that the retry creates one submission. Measure both the time researchers spend submitting a log and the time reviewers spend checking it.

### Later offline features

**Offline archive access.** Sync a read-only copy of the full archive to the device, including the searchable log runs and their original logs. Show when the download is complete and when it last synced. Keep the last complete copy usable if a refresh is interrupted. A researcher can still browse and open the downloaded archive while new uploads and updates wait for a connection.

**Offline photo capture.** Save the submission and its page photos on the device when the connection drops and show it as pending. Upload and start extraction after reconnecting. Keep the pending page photos until the archive confirms the PDF was saved and passed its rendering check. Use the same submission ID for retries to avoid duplicates. Test by taking a photo offline, reopening the capture screen, and reconnecting.

Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later.
