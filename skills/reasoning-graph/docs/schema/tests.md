# Tests and Result Evidence

Use this page as the shape and example reference for `test` nodes. Usage policy lives in `../../SKILL.md`.

## Test node shape

```json
{
  "id": "T1",
  "type": "test",
  "text": "Run the decisive verification"
}
```

A `test` node is a procedure. It is not evidence by itself.

## Result pattern

```txt
A1 --prompts--> T1
T1 --leads_to--> E9
E9 --supports|contradicts--> A1
```

Put `confidence` on result evidence when observation, scripts, OCR, external services, or manual transcription could be wrong.

## Examples

### Proposed check

```json
{
  "nodes": [
    {"id": "A1", "type": "assumption", "text": "The service is reading stale config", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"}
  ],
  "edges": [
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"}
  ]
}
```

### Check with supporting result

```json
{
  "nodes": [
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"},
    {"id": "E1", "type": "evidence", "text": "Startup logs show config mtime before deploy", "confidence": 0.95}
  ],
  "edges": [
    {"id": "T1-E1", "from": "T1", "to": "E1", "type": "leads_to"},
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4}
  ]
}
```

### Inconclusive result

```json
{
  "nodes": [
    {"id": "T2", "type": "test", "text": "Replay request with debug headers"},
    {"id": "E2", "type": "evidence", "text": "Replay was inconclusive because fixture token expired", "confidence": 0.9}
  ],
  "edges": [
    {"id": "T2-E2", "from": "T2", "to": "E2", "type": "leads_to"}
  ]
}
```

## Patch example: recorded result

Expansion patches add result nodes and connect them to the existing test node.

```json
{
  "nodes": [
    {"id": "E1", "type": "evidence", "text": "Startup logs show config mtime before deploy", "confidence": 0.95}
  ],
  "edges": [
    {"id": "T1-E1", "from": "T1", "to": "E1", "type": "leads_to"},
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4}
  ],
  "no_new_work_reason": "Result only updates ranking; no new follow-up branch needed."
}
```

## Validation checklist

- Tests are not evidence by themselves.
- Result nodes, not test nodes, support or contradict claims.
- Use `test --leads_to--> result` for recorded outcomes.
- Inconclusive checks add result evidence explaining why the check did not settle the claim.
- Use `no_new_work_reason` when a result only changes score/ranking and creates no new frontier work.
- Use `exhaustion_reason` only when marking a node or family `exhausted: true`.
