# Tests and Result Evidence

Use this page as the shape and example reference for `test` nodes. Usage policy lives in `../../SKILL.md`.

## Test node shape

```json
{
  "id": "T1",
  "type": "test",
  "text": "Run the decisive verification",
  "status": "proposed"
}
```

`status` values:

```txt
proposed      recommended next check; not evidence
performed     check ran; attach result evidence or derived nodes
inconclusive  check ran but did not settle the claim
```

Only `test` nodes may use `status`.

## Result pattern

```txt
A1 --prompts--> T1
T1 --leads_to--> E9
E9 --supports|contradicts--> A1
```

Put `confidence` on result evidence when observation, scripts, OCR, external services, or manual transcription could be wrong.

## Examples

### Proposed test

```json
{
  "nodes": [
    {"id": "A1", "type": "assumption", "text": "The service is reading stale config", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup", "status": "proposed"}
  ],
  "edges": [
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"}
  ]
}
```

### Performed test with supporting result

```json
{
  "nodes": [
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup", "status": "performed"},
    {"id": "E1", "type": "evidence", "text": "Startup logs show config mtime before deploy", "confidence": 0.95}
  ],
  "edges": [
    {"id": "T1-E1", "from": "T1", "to": "E1", "type": "leads_to"},
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4}
  ]
}
```

### Inconclusive test

```json
{
  "nodes": [
    {"id": "T2", "type": "test", "text": "Replay request with debug headers", "status": "inconclusive"},
    {"id": "E2", "type": "evidence", "text": "Replay failed because fixture token expired", "confidence": 0.9}
  ],
  "edges": [
    {"id": "T2-E2", "from": "T2", "to": "E2", "type": "leads_to"}
  ]
}
```

## Patch example: recorded result

Status changes are existing-node updates. Update the test node in state, then use the expansion patch to add result nodes and record the touched node in `updated_nodes`.

```json
{
  "nodes": [
    {"id": "E1", "type": "evidence", "text": "Startup logs show config mtime before deploy", "confidence": 0.95}
  ],
  "edges": [
    {"id": "T1-E1", "from": "T1", "to": "E1", "type": "leads_to"},
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4}
  ],
  "updated_nodes": [{"id": "T1", "fields": ["status"]}],
  "no_new_work_reason": "Result only updates ranking; no new follow-up branch needed."
}
```

## Validation checklist

- `status` appears only on `test` nodes.
- Proposed tests are not evidence.
- Performed or inconclusive tests add result `evidence` or `derived` nodes when there is an observable result.
- Result nodes, not test nodes, support or contradict claims.
- Use `test --leads_to--> result` for recorded outcomes.
- Keep original test id when updating status so audit trail stays connected.
- Use `no_new_work_reason` when result only changes score/ranking and creates no new frontier work.
- Use `exhaustion_reason` only when marking a node or family `exhausted: true`.
