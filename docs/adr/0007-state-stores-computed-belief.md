---
status: accepted
amends: 0004-local-input-computed-belief-override.md
---

# The state stores computed belief on each claim

## Context

ADR 0006 made `state.json` the agent's working memory. ADR 0004 kept `belief` out of the state as output-only, so an agent rereading the state saw each claim's `prior` but not its belief, and had to remember to run `beliefs`. The number it most needs to decide what to do next was missing from its memory.

The risk of storing a derived value is a stale or hand-typed copy. An agent that edits an edge by hand and rereads an old `belief: 0.85` may believe it is ready to stop.

## Decision

The CLI writes `belief` on every claim node; nobody else does.

- `record` drops the stored beliefs, validates the patched graph, and writes fresh ones.
- Record patches reject `belief` in `nodes` and `update_nodes`.
- `validate` recomputes beliefs and fails on any stored value that differs, or on `belief` on a goal, constraint, or test. The error names the fix: `reasoning-graph beliefs <state> --write`.
- A claim without a stored `belief` is still valid, so hand-built states and fixtures need not carry one.
- The belief math never reads the stored value. `prior` stays the input and `posterior` the explicit override.

`record` prints nothing about changed beliefs; the agent reads them from the state when it needs them.

## Consequences

- A stale belief cannot reach a stop: `stop`, `audit`, and `stop-review` all validate first, and `stop` ranks from recomputed beliefs anyway.
- Hand edits to scores or edges need `beliefs --write` before the state validates again.
