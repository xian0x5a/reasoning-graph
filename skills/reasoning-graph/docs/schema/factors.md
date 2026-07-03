# Factors: Non-independent Input Groups

Use top-level `factors` when multiple incoming numeric relationships to the same target are not independent. A factor prevents double-counting.

Default model: incoming numeric edges are independent. A factor overrides that default for its listed inputs. Ungrouped incoming edges still count normally.

## Mental model

A factor says:

> These inputs point at the same target, but they share source/cause/logic. Count their combined impact once with this aggregation.

A factor is not a node, edge, claim, proof step, candidate, or frontier item. Renderers may draw virtual factor boxes, but canonical state stores factors as top-level records.

## When to use

Use a factor when two or more inputs to the same target share dependence:

- same source or copied source
- duplicate observation
- repeated logs from one event/request
- same measurement pipeline
- logical overlap between premises
- common latent cause
- one input partly derives from another

## When not to use

Do not use a factor for:

- independent evidence
- visual grouping only
- non-numeric relationships
- candidate grouping or ranking
- connecting unrelated targets
- replacing missing edges

Each `input` must already have, or be added with, the matching relation edge to the same `target`.

## Required shape

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

- `id` — unique factor id
- `relation` — one of `leads_to`, `supports`, `contradicts`
- `target` — node receiving the grouped numeric update
- `inputs` — at least two source node ids, each with a matching edge to `target`
- `aggregation` — combined numeric impact for the group
- `reason` — why the inputs are non-independent

## Aggregation by relation

### `leads_to`: grouped premises

Use `joint_probability` when dependent premises derive the target together.

```json
{
  "nodes": [
    {"id": "A1", "type": "assumption", "text": "Source says X", "prior": 0.8},
    {"id": "B1", "type": "assumption", "text": "Same source implies Y", "prior": 0.75},
    {"id": "D1", "type": "derived", "text": "X and Y explain the result"}
  ],
  "edges": [
    {"id": "A1-D1", "from": "A1", "to": "D1", "type": "leads_to"},
    {"id": "B1-D1", "from": "B1", "to": "D1", "type": "leads_to"}
  ],
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "D1",
      "inputs": ["A1", "B1"],
      "aggregation": {"kind": "joint_probability", "probability": 0.72},
      "reason": "A1 and B1 both depend on the same source, so multiplying 0.8 * 0.75 would overcount confidence."
    }
  ]
}
```

The factor replaces the independent product for `A1` and `B1`. Other ungrouped incoming `leads_to` premises still contribute independently.

### `supports`: grouped positive evidence

Use conditional likelihood when dependent evidence supports a target.

```json
{
  "edges": [
    {"id": "E1-H1", "from": "E1", "to": "H1", "type": "supports"},
    {"id": "E2-H1", "from": "E2", "to": "H1", "type": "supports"}
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

Here the group likelihood ratio is `0.54 / 0.18 = 3`. Do not store that ratio directly; store `if_target_true` and `if_target_false`.

### `contradicts`: grouped negative evidence

Use conditional likelihood when dependent evidence argues against a target.

```json
{
  "edges": [
    {"id": "E3-H1", "from": "E3", "to": "H1", "type": "contradicts"},
    {"id": "E4-H1", "from": "E4", "to": "H1", "type": "contradicts"}
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

For `contradicts`, the implied likelihood ratio must be between 0 and 1.

## Adding or replacing factors in patches

Seed and expansion patches should use `factors` to add or replace factors by `id`. If the `id` is new, the factor is appended. If the `id` already exists, the factor is replaced.

To append an input, submit the full replacement factor with the updated `inputs` and recalibrated `aggregation`. Matching edges must already exist or be added in the same patch.

```json
{
  "edges": [
    {"id": "C1-D1", "from": "C1", "to": "D1", "type": "leads_to"}
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

## Validation rules

- `inputs` length must be at least 2.
- `inputs` must not contain duplicates.
- `target` cannot be an input.
- Every input and target must reference existing nodes.
- Every input must have a matching `relation` edge to `target`.
- Factor inputs cannot overlap for the same `relation` and `target`.
- `leads_to` factors require `joint_probability` aggregation.
- `supports` and `contradicts` factors require `likelihood` aggregation.
- Do not set `effective_truth_cost` or direct `likelihood_ratio` on a factor.
- If the target has explicit `posterior`, that posterior overrides graph-derived evidence and factors for that target.

`update_factors` appears in audit events as the list of factor ids changed by an expansion.

## Common mistakes

- Creating a factor without the matching edges.
- Grouping inputs that are merely similar but independent.
- Using a factor as a visual cluster or candidate bucket.
- Setting `likelihood_ratio` directly on the factor.
- Forgetting to recalibrate aggregation when adding/removing inputs.
- Grouping an input in two factors for the same target and relation.