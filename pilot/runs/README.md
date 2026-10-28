# AI runs

Keep each tool, prompt version, and attempt separate. Suggested layout:

```text
runs/
  <tool>/
    <prompt-id>/
      run-001/
        metadata.json
        output.json
        response.txt       # optional exact response, including prose or invalid JSON
```

Examples of tool slugs are `chatgpt`, `claude`, `gemini`, and `grok`; these are naming examples, not evidence that a tool has been tested. Record the exact model in metadata rather than guessing it from the tool name. A second attempt gets `run-002`, even when the tool and prompt are unchanged.

## Run metadata
Use repository-root-relative paths. Record unknown values as JSON `null`, not guessed values. Suggested fields:

```json
{
  "run_id": "<tool>_<prompt-id>_001",
  "tool": null,
  "model": null,
  "prompt_id": null,
  "prompt_path": null,
  "executed_at": null,
  "operator": null,
  "settings": null,
  "input_records": ["JC1301", "JC1302", "JC1303"],
  "source_reference": null,
  "output_path": "pilot/runs/<tool>/<prompt-id>/run-001/output.json",
  "raw_response_path": null,
  "review_status": "unvalidated"
}
```

## Current sample
[ChatGPT / p001-v1 / run 001](chatgpt/p001-v1/run-001/metadata.json) registers the existing [JC1301–JC1303 JSON](../transcriptions/2020-01-16_JC1301-JC1303.json). Its output stays at the original path so the existing link remains usable. The tool is confirmed as ChatGPT and the exact user prompt is saved as [p001-v1](../prompts/p001-v1.txt). The exact model and execution date remain unknown. Source worksheet: `1.pdf` (provided in chat; not stored in the repository). The repository upload date is not the AI execution date.

## Comparison procedure
1. Use the same approved source pages and the same prompt version across tools when comparing models. Record any unavoidable tool-specific differences.
2. Change one factor at a time when comparing prompts. Keep prior outputs intact.
3. Compare fields by JC identifier, including missing values, overwritten notation, and disagreements. Do not silently repair raw outputs or treat blanks as zero.
4. Keep agreement/disagreement separate from correctness. A researcher checks against the source before a result is marked validated.
5. Record findings with links to the compared run folders; do not claim tools have run or tasks are complete without evidence.
