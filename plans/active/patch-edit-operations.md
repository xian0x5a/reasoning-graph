# Patch edit operations and hand-edit refresh

## Goal

Make one `record` patch able to express any graph change, and give agents one operation that brings a hand-edited `state.json` back in line.

## Intention

In the #34 A/B (Sonnet 5, 22 items), skill runs averaged 5.5 `record` calls and 1.5 Python hand-edits of `state.json`. That's about 7 graph writes per run, and each one costs a full-context turn.

- A patch could only add nodes, edges, and factors, and set node fields. It could not change or remove an edge, remove a node or factor, or drop a field. Agents hand-edited to make those changes.
- A hand-edit skipped the verbatim quote check (`a-porsche-of-course` rewrote O12's quote). It left no event, so a passed review stayed current. When it removed an edge, a later `audit` failed with "add_edges references missing edge id".

Analysis: issue #36 comment 5861985148. Target: about 3 graph writes per run (the first batch plus one per review round).

## Scope & Constraints

- Patch operations:
  - `update_nodes` items take `set` and/or `unset`.
  - `update_edges` takes the same `set`/`unset` shape.
  - `remove_nodes`, `remove_edges`, and `remove_factors` take id lists.
- Immutable fields: node `id` and `type`; edge `id`, `from`, and `to`. Changing an edge's endpoints means removing it and adding a new one.
- Removing a node also removes its incident edges, and the event lists them. Factors are never removed implicitly: validation rejects a factor whose input, target, or input edge is gone, so the agent re-authors or removes it in the same patch.
- Within a patch, apply removals, then updates, then additions.
- A `record` whose patch holds only a `reason` is the refresh after a hand-edit. Every `record` then:
  - re-checks every observation quote, not just the ones the patch touched;
  - adds to its event's `remove_*` lists any object an earlier event added that the state no longer has, so `audit` stays consistent;
  - recomputes beliefs, refreshes the view, and makes any earlier review stale (existing behavior).
- Objects added by hand stay untraced, like the goal from `init`.
- Remove `beliefs --write`, which the refresh replaces. No compatibility path.
- Audit replays additions and removals in order. An id may be re-added after it is removed. Any object an event added and no later event removed must exist in the final state.

## Work Plan

1. Tests first (`tests/cli/test_patch_operations.py`) and a port of `test_stale_belief_fails_validation_until_refreshed`. Watch them fail.
2. CLI: patch schema, patch application, trace reconciliation, re-checking every quote, audit replay, removing `beliefs --write`, the stale-belief message.
3. Docs:
   - `skills/reasoning-graph/SKILL.md`: patch operations, record once per checkpoint, the hand-edit refresh.
   - `skills/reasoning-graph/docs/driver.md`: record patch, events, and audit sections.
   - ADR 0008.

## Validation

- `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`
- End-to-end smoke on the reinstalled tool, in this order:
  1. `init`, then `record`.
  2. A patch with an update, an unset, and a removal.
  3. A hand-edit, then a reason-only `record`.
  4. `review`, `stop`, `validate`, then `audit`.

## Decisions

- The refresh is a reason-only `record` rather than a new command. It keeps one write path, and any later `record` also heals a hand-edit.
- Removing a node cascades to its edges but not its factors. An edge without its node has no meaning, but a factor's calibrated aggregation has to be re-authored.

## Follow-ups (not in scope)

- Store a graph digest in review events, so a hand-edit made after a review without a `record` still makes the review stale.

## Progress

- [x] 1. Tests
- [x] 2. CLI
- [ ] 3. Docs
