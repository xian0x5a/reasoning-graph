# Add Reasoning Graph Fixture Matrix

## Goal

Create durable test fixtures for valid states, invalid states, expansion patches, and stable CLI outputs so future changes have broader regression coverage than ad-hoc temp JSON.

## Scope

- Add `tests/fixtures/valid/` state fixtures.
- Add `tests/fixtures/invalid/validate/` validation-failure fixtures.
- Add `tests/fixtures/invalid/audit/` audit-failure fixtures.
- Add `tests/fixtures/patches/` expansion patch fixtures.
- Add `tests/fixtures/golden/` deterministic CLI output snapshots.
- Add fixture matrix tests and patch round-trip tests.

## Findings

Fixture work exposed one real audit gap: a stop event could follow a popped frontier item that was never expanded or selected. The audit now rejects that unresolved pending pop.

## Validation

- `python -m py_compile skills/reasoning-graph/scripts/rg.py skills/reasoning-graph/scripts/reasoning_graph/*.py`
- `python -m unittest discover -s tests/scripts` → 51 tests passed
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py stop-review tests/reasoning-graph-strict-good.json`

## Outcome

Fixture matrix now covers schema validation, CLI validation/audit behavior, JSON Schema compatibility, golden outputs, and applying patch fixtures to a popped branch.
