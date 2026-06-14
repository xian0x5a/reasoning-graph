# Factors for Correlated Updates

## Goal

Introduce top-level `factors` as virtual relation/factor records for correlated `leads_to`, `supports`, and `contradicts` inputs.

## Scope & Constraints

- Keep existing `premise_groups` working as legacy/canonical-compatible input.
- `factors` are not graph nodes, not frontier items, and not truth-bearing claims.
- `leads_to` factors use `joint_probability` aggregation.
- `supports`/`contradicts` factors use conditional likelihood aggregation only: `if_target_true` / `if_target_false`.
- Grouped member edge updates are replaced by factor aggregation; ungrouped inputs still combine normally.

## Work Plan

1. Update mapped pseudocode for model, validation, cost, CLI, and audit behavior.
2. Add factor constants/helpers.
3. Validate factor schema, references, overlap, aggregation semantics, and posterior override warnings.
4. Compute factor effects in truth costs.
5. Allow expansion patches to upsert factors and audit factor events.
6. Update skill docs and tests.
7. Run tests.

## Validation

- `python -m pytest tests/scripts/test_rg_basic.py`

## Progress

- Plan created.
- Updated mapped pseudocode for factors.
- Added factor constants, validation, costs, expand/audit event handling, and virtual factor rendering.
- Updated skill docs.
- Added factor cost/validation/expand/audit tests.
- Validation run: `python -m pytest tests/scripts/test_rg_basic.py -q` passes.

## Outcomes & Retrospective

Implemented `factors` as virtual relation records while keeping `premise_groups` compatible. Factor likelihood aggregation uses conditional `if_target_true` / `if_target_false`; direct factor `likelihood_ratio` is rejected.
