# Report and Presentation Metadata

Use optional `report` metadata when graph/presentation mode needs a readable human report. This is presentation metadata only; source of truth remains `nodes`, `edges`, `frontier`, and optional `events`.

## Report shape

```json
"report": {
  "candidates": [
    {
      "id": "CS1",
      "name": "Candidate label",
      "belief": 0.45,
      "truth_cost": 0.798508,
      "search_cost": 2.24,
      "weight": 0.72,
      "path_nodes": ["E1", "D2", "CS1"],
      "why": "Explains the most evidence with lowest constraint tension",
      "next_test": "Run the decisive verification"
    }
  ],
  "winning_path": ["Evidence A", "Assumption B", "Derived C", "Candidate D"],
  "next_verification": "..."
}
```

Do not encode rank words such as `Best:`, `Second:`, `Third:`, or `Weak:` in candidate `name` or node `text`. Frontier rank is derived by sorting items by `search_cost`; candidate belief ranking is derived from `truth_cost` or `belief`. Renderers can display ordinal rank.

Avoid storing a `rank` field unless ordering comes from an external criterion that is not derivable from cost/belief.

## Candidate display metadata

Do not put `status` on `candidate_solution` nodes. Candidate rank/viability is derived from belief/effective truth cost, search cost, goal `answers` edges, and `answer_kind`.

If the candidate table needs labels such as viable or contradicted, express them in `why`, `next_test`, likelihood edges, or graph relationships, not node `status`.

Optional `path_nodes` on a candidate lists the main node IDs highlighted when a report viewer focuses that candidate. Renderers may include upstream support evidence/constraints for positive path nodes so entry evidence remains visible. Contradicting evidence/test nodes may be highlighted when explicitly listed, but should not automatically pull in their own upstream evidence unless the UI has a separate “why rejected” mode.

If `path_nodes` is omitted, viewers should conservatively focus the candidate node and directly connected support where possible.

## Weights and probabilities

Do not present computed weights as calibrated posterior probabilities. If useful, compute:

```txt
belief = exp(-effective_truth_cost)
weight = belief / sum(belief of displayed candidates)
```

Label `weight` as relative among displayed candidates, not a calibrated real-world probability. Use `posterior` only when explicit evidence/test updates a prior/confidence and uncertainty remains clearly labeled.

## Presentation views

Use optional `presentation` metadata for curated graph/report views.

```json
"presentation": {
  "include_nodes": ["E1", "E2", "A1", "CS1"],
  "highlight_nodes": ["E1", "A1", "CS1"],
  "dim_nodes": ["CS2", "CS3"],
  "title": "Why candidate 1 wins",
  "layout_hint": "evidence-left-candidates-right"
}
```

Baseline HTML uses the fixed graph heading “Best explanation graph”. `presentation.title` may describe the story for custom renderers, but should not replace the default graph heading.

Presentation views may omit low-value nodes for readability. They must not introduce claims absent from the reasoning state.