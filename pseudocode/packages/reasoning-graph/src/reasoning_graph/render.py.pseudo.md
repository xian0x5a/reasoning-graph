# Reasoning Graph Rendering

## Intent

Render reasoning graph state as Mermaid and self-contained HTML reports.

## Behavior

```pseudo
to_mermaid(state, include_nodes):
  choose full or presentation node set
  render grouped nodes, virtual factor nodes for included factors, typed edges, styles, and click anchors

html_document(state, mermaid_source, render_mode):
  render answer summary, goal policy, candidate table, evidence/constraint-aware node detail cards, filters, focus controls, presentation graph, and audit graph
  by default, render Mermaid source and load Mermaid in the browser for better graph layout
  if render_mode is offline, render deterministic inline SVG fallback without CDN/network access and keep Mermaid source in collapsible source blocks
  use graph state/report metadata only; do not invent claims
```

## Required node scores and edge reasoning

Compute truth costs from the full graph before presentation filtering. Display effective belief on compact claim nodes, including inherited-only claims; goals, constraints, and tests render without a belief line. Detail cards distinguish effective belief, local prior, and posterior override, and include escaped incident-edge reasoning.
