# Small-dataset pilot

## Compare AI tools and prompts

- [Prompt versions](prompts/README.md): save the exact instructions used, including follow-up messages.
- [AI runs](runs/README.md): separate results by tool, prompt version, and attempt, with model and source details in `metadata.json`.
- [Current sample run record](runs/chatgpt/p001-v1/run-001/metadata.json): ChatGPT with [prompt p001-v1](prompts/p001-v1.txt); the exact model and execution date remain unknown.

For a new test, use `runs/<tool>/<prompt-id>/run-001/` with `metadata.json` and `output.json`. Keep the original response when possible. The current JSON remains at its existing link and is referenced by its run record.

## Status
**Draft, unvalidated transcription.** This is an initial sample for researcher review; it has not been checked against the source scan or compared across AI tools.

## Current sample
- [2020-01-16_JC1301-JC1303.json](transcriptions/2020-01-16_JC1301-JC1303.json)
- Source date as transcribed: `1/16/2020`.
- Sample identifiers: JC1301, JC1302, and JC1303.
- The user-supplied JSON values and structure are preserved, including blanks, overwritten-value markers, units, and annotations. No scientific values have been inferred or corrected.
- Source worksheet filename: `1.pdf`, supplied in chat. The scan is not uploaded to this repository; approved shared-storage link is not yet recorded.
- Extraction tool: ChatGPT. Exact model: unknown. User prompt: [p001-v1](prompts/p001-v1.txt).

## Questions for researcher review
1. Should the composition variable `x` remain within `Compound`, or map to the separate `X` column? The separate column is blank in this draft.
2. What are the intended values behind `0.0[overwritten]5` and `0.[overwritten]`? Preserve these transcriptions until the source is reviewed.
3. Reference notes list `Pd`, while the formula and table use `Pb`. Check the source before deciding whether this is a transcription error.
4. Confirm what `/` means in the JC1303 Pb field; it has not been converted to zero or null.
5. Confirm the meaning and units of `1:20:3` and the right-margin annotations.

## Source-sheet naming
Keep one JSON per source sheet, using `YYYY-MM-DD_<first-JC>-<last-JC>.json` where the identifiers and date are known. The initial supplied transcription stays in `transcriptions/`; save new tool-specific outputs under the run folders described above. Add reviewed corrections separately in `validated/` when confirmed. Keep scans in the lab-approved storage location and record their source reference.

Blank measured, furnace, load, and timestamp fields mean only that the supplied draft contains no value; they do not establish that an event did not occur. Do not mark implementation tasks complete based on this sample alone.
