# Factors

`factors` are top-level records for grouping dependent incoming numeric edges. Use this page as the shape and example reference; usage policy lives in `../../SKILL.md`.

## Factor shape

```json
{
  "id": "F1",
  "relation": "leads_to",
  "target": "D1",
  "inputs": ["A1", "B1"],
  "aggregation": {"kind": "joint_probability", "probability": 0.72},
  "reason": "A1 and B1 share the same source."
}
```

Fields:

- `id` — unique factor id.
- `relation` — `leads_to`, `supports`, or `contradicts`.
- `target` — node receiving the grouped numeric update.
- `inputs` — two or more source node ids.
- `aggregation` — combined numeric impact for the group.
- `reason` — short explanation for why these inputs are dependent.

Each input must have a matching edge to the same `target` with the same `relation`.

## Aggregation shapes

### `leads_to`

```json
"aggregation": {"kind": "joint_probability", "probability": 0.72}
```

`probability` is the calibrated joint probability for the grouped premises.

### `supports`

```json
"aggregation": {"kind": "likelihood", "if_target_true": 0.54, "if_target_false": 0.18}
```

The implied likelihood ratio must be greater than `1`.

### `contradicts`

```json
"aggregation": {"kind": "likelihood", "if_target_true": 0.1, "if_target_false": 0.5}
```

The implied likelihood ratio must be between `0` and `1`.

Do not store `likelihood_ratio` directly. Store `if_target_true` and `if_target_false`.

## Examples

### Grouped `leads_to` premises

```json
{
  "nodes": [
    {"id": "A1", "type": "assumption", "text": "Source says X", "prior": 0.8},
    {"id": "B1", "type": "assumption", "text": "Same source implies Y", "prior": 0.75},
    {"id": "D1", "type": "derived", "text": "X and Y explain the result", "probability": 1.0}
  ],
  "edges": [
    {"id": "A1-D1", "from": "A1", "to": "D1", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."},
    {"id": "B1-D1", "from": "B1", "to": "D1", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."}
  ],
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "D1",
      "inputs": ["A1", "B1"],
      "aggregation": {"kind": "joint_probability", "probability": 0.72},
      "reason": "A1 and B1 both depend on the same source."
    }
  ]
}
```

### Grouped supporting evidence

```json
{
  "edges": [
    {"id": "E1-H1", "from": "E1", "to": "H1", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."},
    {"id": "E2-H1", "from": "E2", "to": "H1", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."}
  ],
  "factors": [
    {
      "id": "F2",
      "relation": "supports",
      "target": "H1",
      "inputs": ["E1", "E2"],
      "aggregation": {"kind": "likelihood", "if_target_true": 0.54, "if_target_false": 0.18},
      "reason": "E1 and E2 are two log lines from the same failed request."
    }
  ]
}
```

### Grouped contradicting evidence

```json
{
  "edges": [
    {"id": "E3-H1", "from": "E3", "to": "H1", "type": "contradicts", "reasoning": "The observed signal is less likely when the target claim is true."},
    {"id": "E4-H1", "from": "E4", "to": "H1", "type": "contradicts", "reasoning": "The observed signal is less likely when the target claim is true."}
  ],
  "factors": [
    {
      "id": "F3",
      "relation": "contradicts",
      "target": "H1",
      "inputs": ["E3", "E4"],
      "aggregation": {"kind": "likelihood", "if_target_true": 0.1, "if_target_false": 0.5},
      "reason": "E3 and E4 are two views of the same negative check."
    }
  ]
}
```

### Replace a factor in a patch

Seed and expansion patches use `factors` to add or replace factors by `id`. To append an input, submit the full replacement factor with the updated `inputs` and recalibrated `aggregation`.

```json
{
  "edges": [
    {"id": "C1-D1", "from": "C1", "to": "D1", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."}
  ],
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "D1",
      "inputs": ["A1", "B1", "C1"],
      "aggregation": {"kind": "joint_probability", "probability": 0.76},
      "reason": "A1, B1, and C1 now form one source-dependent input group."
    }
  ]
}
```

## Validation checklist

- `inputs` has at least two unique node ids.
- `target` is not in `inputs`.
- `target` and every input reference existing nodes.
- Every input has a matching `relation` edge to `target`.
- Factor inputs do not overlap for the same `relation` and `target`.
- `leads_to` uses `joint_probability` with `probability`.
- `supports` and `contradicts` use `likelihood` with `if_target_true` and `if_target_false`.
- `supports` likelihood ratio is `> 1`; `contradicts` likelihood ratio is in `(0, 1)`.
- Factor does not set `effective_truth_cost` or direct `likelihood_ratio`.
- If `target` has explicit `posterior`, that posterior overrides graph-derived factor costs.
