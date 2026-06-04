# Reasoning Graph Rendering

## Intent

Render reasoning graph state as Mermaid and self-contained HTML reports.

## Behavior

```pseudo
to_mermaid(state, include_nodes):
  choose full or presentation node set
  render grouped nodes, typed edges, styles, and click anchors

html_document(state, mermaid_source):
  render answer summary, goal policy, candidate table, node detail cards, filters, focus controls, presentation graph, and audit graph
  use graph state/report metadata only; do not invent claims
```
