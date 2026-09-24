# Fix stop gates and clear open tickets

## Goal

Close the Spooky Manor stop-gate bugs (#29, #30, #31, #32) and the older open tickets (#8–#20) in one run so the with-skill benchmark arm (#33) can start.

## Intention

The with-skill Spooky Manor run reported a hallucinated answer (`Photophone`, HTTP 404) as `solved`. Every mechanical gate passed because:

- the stop policy counted candidates across all goals, so an unanswered leaf goal was invisible;
- stop-review matched the draft against any candidate, not the one for the goal being resolved;
- test expansions could record no result, so the failed probe never entered the graph;
- branching happened in scratch scripts, so the frontier never had anything to rank.

The older tickets are mostly integrity gaps in the same driver/audit path. Fixing them together keeps the contract coherent.

## Scope & Constraints

- Package under `packages/reasoning-graph/`; skill docs under `skills/reasoning-graph/`.
- Tests first for each bug (`tests/cli/` for commands, `tests/integration/` for invariants).
- Remove superseded behavior rather than adding compatibility paths (edge ids, `answer_kind`, patch aliases).
- Keep the probabilistic frontier queue as the core; new gates only make the trace honest, they do not change ranking.
- No benchmark runs in this plan (#33 stays open).

## Work Plan

1. Small integrity fixes: #13 resolver, #11 atomic writes, #8 malformed input, #9 audit purity, #15 indexed lookups.
2. Contract alignment: #12 edge ids, #17 `answer_kind`, #16 patch fields, #10 presentation/view references.
3. Driver trace integrity: #19 forced commands, #20 audit event integrity (single-claim add lists, historical rank checks).
4. Stop gates: #29 unanswered accepted goal + sub-goal representation via `goal --requires--> goal`; #30 answer-to-candidate matching; #31 strict test-result rule; #32 zero-work expansion rule + peak live frontier stat.
5. Docs: SKILL.md granularity rule, `docs/schema/tests.md`, `docs/schema/goals.md`, `docs/driver.md`, `docs/test-scenarios.md`, README smoke flow.
6. Close #14 as stale (pseudocode directory removed in 2fd8b9a); comment status on #18.

## Validation

`uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q` green; fixture matrix updated with the new negative fixtures.

## Progress

- [ ] Step 1
- [ ] Step 2
- [ ] Step 3
- [ ] Step 4
- [ ] Step 5
- [ ] Step 6

## Decisions

- Sub-goals are plain `goal` nodes linked by `parent --requires--> child`; no new node type. A goal counts as answered only when it has an `answers` edge from a candidate and every required sub-goal is answered.
- Inconclusive tests record result `evidence` (already the documented pattern); no separate `inconclusive_reason` escape.
- The strict "no outgoing edge" error applies to `test` expansions only; assumption expansions legitimately add incoming sibling edges.
- Patch `outcome` alias and patch-supplied `updated_nodes` are removed; `factors` + `update_factors` together is rejected.

## Surprises & Discoveries

## Outcomes & Retrospective
