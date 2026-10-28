# Small-dataset pilot

## Status
**Draft, unvalidated transcription.** This is an initial sample for researcher review; it has not been checked against the source scan or compared across AI tools.

## Current sample
- [2020-01-16_JC1301-JC1303.json](transcriptions/2020-01-16_JC1301-JC1303.json)
- Source date as transcribed: `1/16/2020`.
- Sample identifiers: JC1301, JC1302, and JC1303.
- The user-supplied JSON values and structure are preserved, including blanks, overwritten-value markers, units, and annotations. No scientific values have been inferred or corrected.
- Source scan / approved Dropbox link: not provided yet.
- Extraction tool, model, and prompt: not provided yet.

## Questions for researcher review
1. Should the composition variable `x` remain within `Compound`, or map to the separate `X` column? The separate column is blank in this draft.
2. What are the intended values behind `0.0[overwritten]5` and `0.[overwritten]`? Preserve these transcriptions until the source is reviewed.
3. Reference notes list `Pd`, while the formula and table use `Pb`. Check the source before deciding whether this is a transcription error.
4. Confirm what `/` means in the JC1303 Pb field; it has not been converted to zero or null.
5. Confirm the meaning and units of `1:20:3` and the right-margin annotations.

## File organization
Keep one JSON per source sheet, using `YYYY-MM-DD_<first-JC>-<last-JC>.json` where the identifiers and date are known. Retain the original transcription in `transcriptions/`; add reviewed corrections separately in `validated/` when confirmed. Keep scans in the lab-approved storage location and record their source reference.

Blank measured, furnace, load, and timestamp fields mean only that the supplied draft contains no value; they do not establish that an event did not occur. Do not mark implementation tasks complete based on this sample alone.
