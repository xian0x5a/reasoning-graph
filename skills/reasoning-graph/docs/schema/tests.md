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

A result `observation` takes the default score 5. Lower it only when the reading itself is doubtful: a flaky script, OCR, a lossy transcription.

## Examples

### Proposed check

```json
{
  "nodes": [
    {"id": "H1", "type": "hypothesis", "text": "The service is reading stale config"},
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"}
  ],
  "edges": [
    {"from": "H1", "to": "T1", "type": "prompts"}
  ]
}
```

### Check with supporting result

```json
{
  "nodes": [
    {"id": "T1", "type": "test", "text": "Print config path and mtime at startup"},
    {"id": "O1", "type": "observation", "text": "Startup logs show config mtime before deploy"}
  ],
  "edges": [
    {"from": "T1", "to": "O1", "type": "leads_to"},
    {"from": "O1", "to": "H1", "type": "supports", "score": 4, "note": "The config predates the deploy, so the service cannot have read the new one."}
  ]
}
```

### Inconclusive result

```json
{
  "nodes": [
    {"id": "T2", "type": "test", "text": "Replay request with debug headers"},
    {"id": "O2", "type": "observation", "text": "Replay was inconclusive because fixture token expired"}
  ],
  "edges": [
    {"from": "T2", "to": "O2", "type": "leads_to"}
  ]
}
```

### Not runnable here

A check that would settle a claim but cannot be run in this environment stays in the graph with `not_run` set to the reason. It needs no result observation, may not have one, and renders dashed as "test · not run", so the view shows which decisive checks never happened. Never write a result for a check that did not happen.

```json
{"id": "T3", "type": "test", "text": "Compare the body's dental records with Ada's", "not_run": "The case file has no dental records and no exam can be done"}
```

## Patch example: recorded result

A `record` patch adds the result node and connects it to the existing test node.

```json
{
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Startup logs show config mtime before deploy"}
  ],
  "edges": [
    {"from": "T1", "to": "O1", "type": "leads_to"},
    {"from": "O1", "to": "H1", "type": "supports", "score": 4, "note": "The config predates the deploy, so the service cannot have read the new one."}
  ]
}
```

## Result rule

`audit` fails a claimed answer while any `test` node lacks both a result `observation` linked by `test --leads_to--> observation` and a `not_run` reason. While no answer is claimed it lists the gap as something an answer still needs.

A check that ran but did not settle anything (inconclusive, blocked, failed, or skipped midway) is recorded as a result observation describing what happened (see the inconclusive example above); `not_run` is only for a check that cannot be performed here at all. A failed probe of one interpretation usually also adds `result --contradicts--> interpretation`.

## Validation checklist

- Tests carry no belief by themselves.
- Test nodes carry no score; score the result observation instead.
- Result nodes are `observation` only; a conclusion is a separate `hypothesis` reached by `leads_to` from the observation.
- Result observations, not test nodes, support or contradict claims.
- Use `test --leads_to--> observation` for recorded outcomes.
- Inconclusive checks add a result observation explaining why the check did not settle the claim.
- A check that cannot be run here carries `not_run` with the reason and has no result observation, never an invented one.
