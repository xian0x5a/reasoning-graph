---
status: accepted
amends: 0007-state-stores-computed-belief.md
---

# One record patch carries every graph edit

## Context

In the #34 A/B (Sonnet 5, 22 True Detective items), each skill run averaged 5.5 `record` calls and 1.5 Python hand-edits of `state.json`. Every graph write is another turn that re-reads the whole context, and that turn count multiplied the skill's cost to about 6.3× the no-skill arm.

A patch could only add nodes, edges, and factors, and set node fields. Agents hand-edited the JSON for the changes a patch couldn't make: rewording or deleting an edge, dropping a prior, fixing a quote. Those hand-edits:

- skipped the verbatim quote check (`a-porsche-of-course` rewrote an observation's quote);
- left no event, so a passed review stayed current over a graph the reviewer never saw;
- made a later `audit` fail when they removed an edge an earlier event had added.

`beliefs --write` recomputed beliefs after a hand-edit but fixed none of these.

## Decision

- A patch can remove (`remove_nodes`, `remove_edges`, `remove_factors`), change (`update_nodes` and `update_edges` with `set` and `unset`), and add. It applies removals, then updates, then additions.
- Identity fields are fixed: a node's `id` and `type`, and an edge's `id`, `from`, and `to`. Changing one means removing the object and adding a new one.
- Removing a node removes its edges. Factors are never removed implicitly, because a factor's calibrated aggregation has to be re-authored rather than silently dropped.
- Every `record` rechecks every quote and logs as removals any traced object the state no longer holds. A patch holding only `reason` is therefore how a hand-edit is re-synced. It replaces `beliefs --write`, which is removed.
- `audit` replays each record's removals, then its additions, so an object can be removed and later added again.
- The skill asks for one patch per checkpoint (sources read, candidate formed, test result in, review findings fixed), not one per step.

## Consequences

- A review round, or a belief fix that used to need several records or a Python edit, is one `record`.
- A hand-edit that is followed by a `record` gets the same checks as a patch.
- A hand-edit with no `record` after it can still slip past a review. The follow-up is to store a graph digest in review events.
- Objects added by hand stay untraced, like the goal `init` writes.
