# Report and Presentation Metadata

Use this page as the shape and example reference for optional human-facing metadata. Source of truth remains `nodes`, `edges`, `factors`, and `events`.

## `report` shape

```json
"report": {
  "title": "Why candidate 1 wins",
  "answer": "Short final answer for the report",
  "candidates": [
    {
      "id": "CS1",
      "name": "Candidate label",
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
  "dimmed_branches": ["CS2", "CS3"]
}
```

## Computed columns

The rendered candidate table adds `belief` and `weight` from the graph: `belief = exp(-effective_truth_cost)` and `weight = belief / sum(belief of displayed candidates)`. `weight` is relative among displayed candidates, not a calibrated probability.

A report row never carries them. `belief`, `truth_cost`, `effective_truth_cost`, and `weight` in `report.candidates` are rejected.

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
- Store no rank, belief, or weight; the rendered view computes them.
- Candidate viability should come from graph relationships and report text.
- `presentation.include_nodes`, `highlight_nodes`, and `dim_nodes` reference existing node ids.
- Presentation/report metadata does not add claims missing from graph state.
