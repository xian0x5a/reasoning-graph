---
status: done
---

# Fix open issues #10, #11, #12

## Goal

Close the three open issues found while reviewing the candidate-as-hypothesis branch:

- #11: `audit`, `refresh`, and `record` print a raw Python error on a malformed state shape instead of reporting it.
- #10: `goal_policy.accepted_goals` that lists a goal but not the sub-goal it `requires` makes the goal unanswerable, and the error points at the wrong fix.
- #12: lint leftovers (`node_types` unused in `index.py`; `goal_ids` and `accepted_goal_ids` locals shadow the `policy` functions in `validate_state`).

## Intention

A malformed state is an input error the agent can fix, so it must come back as a validation error naming the fix, never as `'str' object has no attribute 'get'`. A sub-goal is part of the goal that requires it, so accepting the goal accepts the sub-goal; listing it again is redundant data that drifts as sub-goals are added mid-run.

## Scope & Constraints

- Package under `packages/reasoning-graph/`; the goal docs under `skills/reasoning-graph/docs/schema/goals.md`.
- `record` keeps building on an invalid hand edit when the patch can apply (`skills/reasoning-graph/docs/driver.md`: "a patch can repair a hand edit").
- Schema errors keep their friendly companions (removed fields named with their replacement, `invalid type 'fact'`); the suite asserts many of them.
- `mermaid` renders without validating by design; it is out of scope.

## Work Plan

1. Regression tests first, written by an independent agent, seen failing for the expected reason.
2. #11: gate the graph rules on the shape.
   - `schema_validation.state_type_errors`: the schema errors whose validator is `type`.
   - Schema: give the node and edge `type` enums `"type": "string"`; add `optional_goals` to `goalPolicy`, so every value the graph rules hash or walk declares its JSON type.
   - `validate_state`: schema errors, then the friendly names (`authored_field_errors`, removed sections), then, only when there is no type error, the graph rules.
   - `authored_field_errors` reads a non-string `type` as no type, since it also runs on patches and on unreadable states.
   - `solutions` is schema-rejected but still read by the graph rules (a crash source): report it as removed, like `stop_policy`, and drop its reference checks. Drop the edge `label` fallback in `validate_state` for the same reason.
   - `record` applies the patch wherever it can, so a patch still repairs a hand edit such as `"score": "4"`. Where it cannot, it says so, like `_upsert_by_id` already does: a state that is not an object, a section that is not a list, a `summary` that is not an object when the patch sets the answer. Items with a non-string id are skipped by the id lookups; validation reports them. `_quote_errors` returns nothing for a state whose nodes are not a list.
   - Remove the graph-rule shape checks the gate makes unreachable.
3. #10: `policy.accepted_goal_ids` adds every goal an accepted goal requires, transitively. `validate_state` calls it instead of its own copy. The error for a candidate outside the accepted goals names the goals and both fixes.
4. #12: drop `node_types`; the shadowing goes with step 3.
5. Docs: `goals.md` (`accepted_goals` meaning, checklist).
6. Independent review of the final diff.

## Validation

- `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q` green.
- `uvx ruff check --select F packages/reasoning-graph/src` clean.
- The issue repros print validation errors, not Python errors.

## Progress

- [x] Step 1 regression tests (independent agent; all failed on the base commit for the bug, except the two pins of behaviour that already worked)
- [x] Step 2 #11
- [x] Step 3 #10
- [x] Step 4 #12
- [x] Step 5 docs
- [x] Step 6 review (independent agent: no correctness findings; about 23,000 wrong-type mutations raised no Python error)

## Decisions

- #11 gate on schema `type` errors only. Rejected: skip the graph rules on any schema error (the issue's suggestion). A probe failed 21 tests: the graph rules give the friendlier message for many schema errors (removed sections and group fields, `invalid type 'fact'`), and one run should list everything to fix. Rejected: harden every reader against every shape; the crash sites are spread over `policy`, `costs`, and `validation`.
- Cost of the type gate, accepted: a wrong JSON type anywhere, even on a field no graph rule reads such as `note: 5`, hides the graph-rule errors until it is fixed. Narrowing the gate to the fields each rule reads would bring back the coupling the gate avoids; a wrong JSON type is rare next to the removed fields and enum values whose messages the gate keeps.
- `record` does not refuse a state with a type error up front: that would stop a patch from repairing a hand edit such as `"score": "4"`, a documented use.
- #10 derive acceptance through `requires`. Rejected: reject a policy that leaves out a required sub-goal; it makes every new `requires` edge invalidate the policy, and the combination it forbids has no use today (the parent can never be answered).

## Surprises & Discoveries

- #11 is wider than the issue lists: a list-valued node `id` or `type`, `accepted_goals` entry, `goal_groups` goal, `solutions` entry, or a non-object `nodes` also raise.

## Outcomes & Retrospective

- #11: `audit`, `refresh`, `record`, and `html` report every wrong-shape state as a schema error, one line per value: errors that only restate a type error on the same value are dropped. The graph rules lost the shape checks the gate covers, and `solutions` is named as removed instead of read.
- #10: accepted goals are the listed ones and everything they require. A required sub-goal takes every accepted-goal check: kind, and naming its candidate in `summary.answer` (documented in `goals.md`). A state that passed with an unnamed sub-goal candidate now fails `audit`, as it already did without a policy.
- #12: `ruff --select F` is clean on the package source. `tests/cli/test_commands.py` still imports `math` unused; out of the issue's scope.
- Follow-ups: `mermaid` renders without validating, so it still raises on a wrong-shape state; the rendering and belief code still fall back to the removed edge `label`.
- Retrospective: the issue's suggested fix (stop on any schema error) looked complete until a probe ran the suite; 21 failures showed the graph rules double as the friendly layer for many schema errors. Probing the cheap option first settled the design faster than reasoning about it.
