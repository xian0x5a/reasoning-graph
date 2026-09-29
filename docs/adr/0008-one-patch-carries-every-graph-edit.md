---
status: accepted
amends: 0007-state-stores-computed-belief.md
---

# One record patch carries every graph edit, and stop checks what it judges

## Context

In the #34 A/B (Sonnet 5, 22 True Detective items), each skill run averaged 5.5 `record` calls and 1.5 Python hand-edits of `state.json`. Every graph write is another turn that re-reads the whole context, and that turn count multiplied the skill's cost to about 6.3× the no-skill arm.

A patch could only add nodes, edges, and factors, and set node fields. Agents hand-edited the JSON for the changes a patch couldn't make: rewording or deleting an edge, dropping a prior, fixing a quote. Those hand-edits:

- skipped the verbatim quote check (`a-porsche-of-course` rewrote an observation's quote);
- left no event, so a passed review stayed current over a graph the reviewer never saw;
- made a later `audit` fail when they removed an edge an earlier event had added.

`beliefs --write` recomputed beliefs after a hand-edit but fixed none of these. `stop` also never validated the graph, and it kept whatever beliefs were stored.

## Decision

- A patch can remove (`remove_nodes`, `remove_edges`, `remove_factors`), change (`update_nodes` and `update_edges` with `set` and `unset`), and add. It applies removals, then updates, then additions.
- Identity fields are fixed: a node's `id` and `type`, and an edge's `id`, `from`, and `to`. Changing one means removing the object and adding a new one. ([ADR 0012](0012-status-is-computed-not-stored.md) removed the edge `id`: an edge is named by its ends.)
- Removing a node removes its edges. Factors are never removed implicitly, because a factor's calibrated aggregation has to be re-authored rather than silently dropped.
- `record`, `refresh`, `review`, and `stop` events store a `graph_digest`: a hash of nodes (without `belief`), edges, factors, and the gate policies. ([ADR 0012](0012-status-is-computed-not-stored.md) removed the events, the digest, and `stop`: a hand edit is checked by the next command and no longer logged, and `audit` is the read-only check.)
- A digest that differs from the last `record` or `refresh` event marks a hand-edit. `refresh`, `record`, and `stop` all take one in: the graph must validate and every quote must match, then a `refresh` event lists the removed objects. `refresh` does only that, plus rewriting beliefs and the view. It replaces `beliefs --write`, which is removed.
- `record` and `stop` take the edit in themselves rather than refusing and sending the agent to `refresh`: refusing only cost a turn, because the review gate already catches a hand-edit after a review.
- A review is stale when its digest differs from the current graph's, whether the change came from a patch or a hand-edit.
- `stop` validates the graph and computes every belief itself; stored beliefs are overwritten. `audit` fails when the graph changed after `stop`.
- `audit` replays each record's removals, then its additions, so an object can be removed and later added again.
- The skill asks for one patch per checkpoint (sources read, candidate formed, test result in, review findings fixed), not one per step.

## Consequences

- A review round, or a belief fix that used to need several records or a Python edit, is one `record`.
- A hand-edit can't reach a stop unchecked: it passes the same checks as a patch, is logged, and needs a fresh review.
- The digest makes accidental and casual tampering visible, but the trace is still a file the agent can write. It doesn't stop a deliberate forgery that recomputes digests.
- Objects added by hand stay untraced, like the goal `init` writes.
