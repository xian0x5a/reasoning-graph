---
status: accepted
amends:
  - 0010-computed-belief-is-for-the-reader.md
  - 0012-status-is-computed-not-stored.md
---

# The state is the graph

## Context

The state had three optional sections written for the reader: `report` (an answer text, a row per candidate with `why` and `next_test`, a winning path, a next verification), `presentation` (nodes to include, highlight or dim) and `view` (a winning path, dimmed branches).

- Each was a second copy of something the graph holds. A candidate is a node, its reason is its edges and notes, and a next check is a `test` node without a result.
- A copy can disagree with the graph. `report.answer` needed its own check against `summary.answer`, and every node reference in the three sections needed a check that the node exists.
- No agent wrote one. In the final states of three runs of the resume loop (42 states, Sonnet 5.5, 14 True Detective items), `report`, `presentation` and `view` appear 0 times.
- The candidate table of the HTML view was already derived from the graph. Its `Why` and `Next test` columns read `report` and were always empty.

## Decision

- The state holds `summary`, `nodes`, `edges`, `factors`, `goal_policy` and `goal_groups`.
- The one fact outside the nodes and edges is the claim, `summary.answer`. It names which candidate is the answer, and the graph cannot say that by itself: the answer is the candidate the agent names, not the one that ranks first.
- `report`, `presentation` and `view` are removed. A state that carries one fails validation with a message that says where the content goes: the answer is `summary.answer`, a reason is a `note` on the node or edge, a next check is a `test` node.
- The rendered view derives everything it shows from the graph and the claim.
- `mermaid --view` and `mermaid --grouped` are removed. There is one graph, the full one, grouped by node type.

## Consequences

- Nothing the reader sees can disagree with the graph.
- A reader cannot be given a curated subset of the graph. The focus control of the HTML view highlights the derivation of one candidate, and the whole graph stays on the page.
- A reason that belongs to no node or edge has no place in the state. It goes in the final response.
- Old states that carry one of the three sections fail validation and are not migrated.
