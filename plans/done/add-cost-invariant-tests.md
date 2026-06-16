# Add Cost Invariant Tests

## Goal

Add small deterministic invariant tests for core reasoning-graph cost semantics without introducing fuzzing or broad property-test infrastructure.

## Invariants Covered

- Explicit `posterior` overrides prior, graph evidence updates, and grouped factors.
- Supporting likelihood updates lower truth cost.
- Contradicting likelihood updates raise truth cost.
- Grouped support factors replace member likelihood updates instead of double-counting them.
- Explanatory support edges without numeric likelihood do not change truth cost.
- Validator reports invalid probability/cost errors instead of throwing.

## Validation

- `python -m unittest tests.scripts.test_rg_invariants`
- `python -m unittest discover -s tests/scripts` → 57 tests passed
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py stop-review tests/reasoning-graph-strict-good.json`

## Outcome

Cost semantics now have direct invariant coverage separate from CLI regression tests and broad fixtures.
