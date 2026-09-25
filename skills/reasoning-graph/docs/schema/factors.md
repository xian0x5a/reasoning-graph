# Factors

`factors` are top-level records for grouping dependent incoming numeric edges. Use this page as the shape and example reference; usage policy lives in `../../SKILL.md`.

## Factor shape

```json
{
  "id": "F1",
  "relation": "leads_to",
  "target": "H3",
  "inputs": ["H1", "H2"],
  "aggregation": {"kind": "joint_probability", "probability": 0.72},
  "reason": "H1 and H2 share the same source."
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
    {"id": "H1", "type": "hypothesis", "text": "Source says X", "prior": 0.8},
    {"id": "H2", "type": "hypothesis", "text": "Same source implies Y", "prior": 0.75},
    {"id": "H3", "type": "hypothesis", "text": "X and Y explain the result"}
  ],
  "edges": [
    {"id": "H1-H3", "from": "H1", "to": "H3", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."},
    {"id": "H2-H3", "from": "H2", "to": "H3", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."}
  ],
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "H3",
      "inputs": ["H1", "H2"],
      "aggregation": {"kind": "joint_probability", "probability": 0.72},
      "reason": "H1 and H2 both depend on the same source."
    }
  ]
}
```

### Grouped `supports` edges

```json
{
  "edges": [
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."},
    {"id": "O2-H1", "from": "O2", "to": "H1", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."}
  ],
  "factors": [
    {
      "id": "F2",
      "relation": "supports",
      "target": "H1",
      "inputs": ["O1", "O2"],
      "aggregation": {"kind": "likelihood", "if_target_true": 0.54, "if_target_false": 0.18},
      "reason": "O1 and O2 are two log lines from the same failed request."
    }
  ]
}
```

### Grouped `contradicts` edges

```json
{
  "edges": [
    {"id": "O3-H1", "from": "O3", "to": "H1", "type": "contradicts", "reasoning": "The observed signal is less likely when the target claim is true."},
    {"id": "O4-H1", "from": "O4", "to": "H1", "type": "contradicts", "reasoning": "The observed signal is less likely when the target claim is true."}
  ],
  "factors": [
    {
      "id": "F3",
      "relation": "contradicts",
      "target": "H1",
      "inputs": ["O3", "O4"],
      "aggregation": {"kind": "likelihood", "if_target_true": 0.1, "if_target_false": 0.5},
      "reason": "O3 and O4 are two views of the same negative check."
    }
  ]
}
```

### Replace a factor in a patch

Seed and expansion patches use `factors` to add or replace factors by `id`. To append an input, submit the full replacement factor with the updated `inputs` and recalibrated `aggregation`.

```json
{
  "edges": [
    {"id": "H4-H3", "from": "H4", "to": "H3", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."}
  ],
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "H3",
      "inputs": ["H1", "H2", "H4"],
      "aggregation": {"kind": "joint_probability", "probability": 0.76},
      "reason": "H1, H2, and H4 now form one source-dependent input group."
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
- If `target` has explicit `posterior`, that posterior overrides factor costs computed from the graph.
