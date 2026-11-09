# Researcher Photo Upload Pilot Design

This pilot builds on the archive workflow described in the [MVP design](../DESIGN.md).

**Researcher photo-upload pilot.** Researchers take a photo of a paper log and upload it in the app. The app checks that the whole log is readable, converts it to PDF, and verifies that every page renders. It asks for a retake if the photo is blurry or cropped. After upload, the app shows submission status and carries the PDF through the same extraction, review, and import workflow tested in the MVP.

**Reuse the processing workflow.** Once an uploaded photo becomes a PDF, send it through the same risk assessment, extraction, human review, and import steps used for the existing Drive logs.

**Shared review.** Use the shared review server and reviewer accounts from the MVP to process submissions from the pilot.

Before rolling out photo uploads, confirm who handles exceptions. Test on actual phone photos, including pages with several runs and notes in the margins. Measure both the time researchers spend submitting a log and the time reviewers spend checking it.

### Later offline features

**Offline archive access.** Sync a read-only copy of the full archive to the device, including the searchable log runs and their original logs. Show when the download is complete and when it last synced. Keep the last complete copy usable if a refresh is interrupted. A researcher can still browse and open the downloaded archive while new uploads and updates wait for a connection.

**Offline photo capture.** Save the photo on the device when the connection drops and show it as pending. Upload and start extraction after reconnecting. Keep the pending photo until the archive confirms the PDF was saved and passed its rendering check. Use the same submission ID for retries to avoid duplicates. Test by taking a photo offline, reopening the capture screen, and reconnecting.

Meanwhile, instrument data lives on lab computers and Dropbox, and some files are also shared in Slack. Those overlapping digital sources can be reconciled later.
