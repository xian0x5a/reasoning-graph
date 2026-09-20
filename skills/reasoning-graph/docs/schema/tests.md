# Tests and Result Evidence

Use this page as the shape and example reference for `test` nodes. Usage policy lives in `../../SKILL.md`.

## Test node shape

```json
{
  "id": "T1",
  "type": "test",
  "text": "Run the decisive verification",
  "confidence": 0.95
}
```

A `test` node is a procedure. It is not evidence by itself.

## Result pattern

```txt
A1 --prompts--> T1
T1 --leads_to--> E9
E9 --supports|contradicts--> A1
```

Include `confidence` on result evidence because observation, scripts, OCR, external services, or manual transcription could be wrong.

## Example: check and supporting result

```json
{
  "nodes": [
    {"id": "A1", "type": "assumption", "text": "Service reads stale config", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Read config mtime", "confidence": 0.95},
    {"id": "E1", "type": "evidence", "text": "Config predates deployment", "confidence": 0.95}
  ],
  "edges": [
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts", "reasoning": "Staleness can be checked by reading the timestamp."},
    {"id": "T1-E1", "from": "T1", "to": "E1", "type": "leads_to", "reasoning": "The check produced this timestamp observation."},
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4, "reasoning": "An old timestamp favors stale config, with reliability included in the ratio."}
  ]
}
```

For an expansion patch when `A1` and `T1` already exist, add only `E1` and its
two edges. If it creates no new work, include `no_new_work_reason`.
An inconclusive check still adds result evidence explaining the limitation
(for example, an expired token), without a numeric claim update.

## Validation checklist

- Tests are not evidence by themselves.
- Result nodes, not test nodes, support or contradict claims.
- Use `test --leads_to--> result` for recorded outcomes.
- Inconclusive checks add result evidence explaining why the check did not settle the claim.
- Use `no_new_work_reason` when a result only changes score/ranking and creates no new frontier work.
- Use `exhaustion_reason` only when marking a node or family `exhausted: true`.
