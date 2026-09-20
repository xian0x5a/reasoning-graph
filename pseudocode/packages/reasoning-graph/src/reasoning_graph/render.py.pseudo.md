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

Display the score field name and value on compact graph nodes that carry one; goal and constraint stipulations render without a score line. Include escaped incident-edge reasoning in node detail cards.
