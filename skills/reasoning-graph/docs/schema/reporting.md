# Report and Presentation Metadata

Use this page as the shape and example reference for optional human-facing metadata. Source of truth remains `nodes`, `edges`, `frontier`, `factors`, and `events`.

## `report` shape

```json
"report": {
  "title": "Why candidate 1 wins",
  "answer": "Short final answer for the report",
  "candidates": [
    {
      "id": "CS1",
      "name": "Candidate label",
      "belief": 0.45,
      "truth_cost": 0.798508,
      "effective_truth_cost": 0.798508,
      "search_cost": 2.24,
      "weight": 0.72,
      "path_nodes": ["O1", "H2", "CS1"],
      "why": "Explains the most observations with lowest constraint tension",
      "next_test": "Run the decisive verification"
    }
  ],
  "winning_path": ["Observation A", "Hypothesis B", "Hypothesis C", "Candidate D"],
  "next_verification": "Run the decisive verification"
}
```

`report.candidates[].path_nodes` lists node ids highlighted when a viewer focuses that candidate. If omitted, viewers should focus the candidate and directly connected support where possible.

## `presentation` shape

```json
"presentation": {
  "include_nodes": ["O1", "O2", "H1", "CS1"],
  "highlight_nodes": ["O1", "H1", "CS1"],
  "dim_nodes": ["CS2", "CS3"],
  "title": "Why candidate 1 wins",
  "layout_hint": "observations-left-candidates-right"
}
```

Presentation views are curated and may omit low-value nodes for readability. They must not introduce claims absent from the reasoning state.

## `view` shape

```json
"view": {
  "winning_path": ["O1", "H2", "CS1"],
  "dimmed_branches": ["CS2", "CS3"],
  "frontier": ["F1", "F2"]
}
```

## Weight formula

When useful, compute candidate display weight from displayed candidates:

```txt
belief = exp(-effective_truth_cost)
weight = belief / sum(belief of displayed candidates)
```

`weight` is relative among displayed candidates, not calibrated real-world probability. Reported `belief` is computed from the current graph and is not written into node scores. A stored `posterior` is an explicit calibrated override, not the normal result of every likelihood update; use it only to replace the node's calculation deliberately.

## Example

```json
{
  "report": {
    "title": "Cache staleness is most likely",
    "answer": "Most observations point to stale config loaded at startup.",
    "candidates": [
      {
        "id": "CS1",
        "name": "Stale config",
        "belief": 0.67,
        "effective_truth_cost": 0.400478,
        "search_cost": 1.4,
        "weight": 0.78,
        "path_nodes": ["O1", "H1", "CS1"],
        "why": "Deploy-time mtime and restart behavior support this branch.",
        "next_test": "Restart with config hash logging."
      }
    ],
    "winning_path": ["Config mtime observation", "Stale config hypothesis", "Stale config candidate"],
    "next_verification": "Restart with config hash logging."
  },
  "presentation": {
    "include_nodes": ["O1", "H1", "CS1", "CS2"],
    "highlight_nodes": ["O1", "H1", "CS1"],
    "dim_nodes": ["CS2"],
    "title": "Why stale config wins",
    "layout_hint": "observations-left-candidates-right"
  }
}
```

## Validation checklist

- Do not encode rank words such as `Best`, `Second`, or `Weak` in candidate `name` or node `text`.
- Avoid storing a `rank` field unless ordering comes from an external criterion not derivable from cost or belief.
- Candidate viability should come from graph relationships and report text.
- Use `weight` only as relative display weight among listed candidates.
- `presentation.include_nodes`, `highlight_nodes`, and `dim_nodes` reference existing node ids.
- Presentation/report metadata does not add claims missing from graph state.
