# Tests and Result Observations

Use this page as the shape and example reference for `test` nodes. Usage policy lives in `../../SKILL.md`.

## Test node shape

```json
{
  "id": "T1",
  "type": "test",
  "text": "Run the decisive verification"
}
```

A `test` node is a procedure, so it carries no score and no belief by itself. Its outcome is an `observation` node with its own score.

## Result pattern

```txt
H1 --prompts--> T1
T1 --leads_to--> O9
O9 --supports|contradicts--> H1
```

Result nodes are `observation` only: record what the test showed, not what it means. A conclusion drawn from the observation is a separate `hypothesis` linked `O9 --leads_to--> H2`.

Give the result `observation` a local `prior` accounting for observation, script, OCR, service, or transcription reliability. A scoreless test procedure does not supply a belief source; the result observation needs its own prior.

## Examples

### Proposed check

```json
{
  "nodes": [
    {"id": "H1", "type": "hypothesis", "text": "The service is reading stale config", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"}
  ],
  "edges": [
    {"id": "H1-T1", "from": "H1", "to": "T1", "type": "prompts", "reasoning": "This claim motivates the follow-up check."}
  ]
}
```

### Check with supporting result

```json
{
  "nodes": [
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"},
    {"id": "O1", "type": "observation", "text": "Startup logs show config mtime before deploy", "prior": 0.95}
  ],
  "edges": [
    {"id": "T1-O1", "from": "T1", "to": "O1", "type": "leads_to", "reasoning": "The test produced this observation."},
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "likelihood_ratio": 4, "reasoning": "The observed signal is more likely when the target claim is true."}
  ]
}
```

### Inconclusive result

```json
{
  "nodes": [
    {"id": "T2", "type": "test", "text": "Replay request with debug headers"},
    {"id": "O2", "type": "observation", "text": "Replay was inconclusive because fixture token expired", "prior": 0.9}
  ],
  "edges": [
    {"id": "T2-O2", "from": "T2", "to": "O2", "type": "leads_to", "reasoning": "The test produced this observation."}
  ]
}
```

## Patch example: recorded result

Expansion patches add result nodes and connect them to the existing test node.

```json
{
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Startup logs show config mtime before deploy", "prior": 0.95}
  ],
  "edges": [
    {"id": "T1-O1", "from": "T1", "to": "O1", "type": "leads_to", "reasoning": "The test produced this observation."},
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "likelihood_ratio": 4, "reasoning": "The observed signal is more likely when the target claim is true."}
  ],
  "no_new_work_reason": "Result only updates ranking; no new follow-up branch needed."
}
```

## Strict result rule

Under `stop_policy.severity: "error"` (the `--strict` profile), expanding a popped `test` item must add at least one `observation` node linked by `test --leads_to--> observation`. `expand` rejects the patch otherwise, and `audit` reports the gap as an error on replayed traces; without strict policy it is a warning.

There is no escape field: an inconclusive, blocked, or failed check is recorded as a result observation describing what happened (see the inconclusive example above). A failed probe of one interpretation usually also adds `result --contradicts--> interpretation` so the frontier re-ranks siblings.

## Validation checklist

- Tests carry no belief by themselves.
- Test nodes carry no score; score the result observation instead.
- Result nodes are `observation` only; a conclusion is a separate `hypothesis` reached by `leads_to` from the observation.
- Result observations, not test nodes, support or contradict claims.
- Use `test --leads_to--> observation` for recorded outcomes.
- Inconclusive checks add a result observation explaining why the check did not settle the claim.
- Use `no_new_work_reason` when a result only changes score/ranking and creates no new frontier work.
- Use `exhaustion_reason` only when marking a node or family `exhausted: true`.
