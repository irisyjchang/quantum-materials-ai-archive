# Prompt versions

Store the exact prompts actually used in this folder. Do not reconstruct missing prompts from an output or label a proposed prompt as an executed one.

Use an ID such as `p001-v1`, saved as `p001-v1.txt` (exact prompt text) or `p001-v1.md` (documented prompt). A changed instruction, example, or output format gets a new version. Keep earlier versions so past runs remain reproducible. Multiple tools may reference the same prompt version when its instructions are identical.

For each version, preserve these details in the prompt file or its linked run metadata:
- Prompt ID and purpose.
- Exact system instructions, if known; otherwise explicitly record “not available”.
- Exact user message(s), in order, including follow-up corrections.
- Attached source filenames/page ranges and any variable substitutions.
- Output schema or JSON example supplied to the tool, if any.

## Recorded prompt

[p001-v1.txt](p001-v1.txt) preserves the user-supplied worksheet extraction prompt exactly, including the four quotation marks in requirement 8. It is linked to the [ChatGPT run](../runs/chatgpt/p001-v1/run-001/metadata.json). The exact model, system instructions, and execution date remain unknown. The supplied source filename is `1.pdf`; the scan is not stored in this repository.
