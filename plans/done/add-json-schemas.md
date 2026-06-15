# Add Reasoning Graph JSON Schemas

## Goal

Add machine-readable JSON Schemas for reasoning graph state files and expansion patch files.

## Intention

Give editors, external users, and tests a stable contract independent of Python validator internals.

## Scope & Constraints

- Add schemas under `skills/reasoning-graph/schemas/`.
- Keep Python validator as source of runtime truth for now; schemas should mirror core structure and enums.
- Avoid adding runtime package dependencies.
- Tests may use `jsonschema` only if available, otherwise validate schema files structurally and inspect key invariants.

## Work Plan

1. Create `state.schema.json` covering top-level state, nodes, edges, factors, frontier, events, policies, reports, presentation.
2. Create `patch.schema.json` covering expansion patch inputs.
3. Add tests that schemas parse and key enums/invariants are present; if `jsonschema` is installed, validate the strict-good fixture and a minimal patch.
4. Run full tests and fixture validation/audit.

## Validation

- `python -m unittest discover -s tests/scripts`
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`

## Progress

- Started after doc split commit `e62b8b4`.
- Added `state.schema.json` and `patch.schema.json` under `skills/reasoning-graph/schemas/`.
- Added tests for schema parsing, core enums, fixture validation, patch validation, and invalid examples.
- Documented schema locations in README and quick skill references.
- Validation passed: unittest suite, fixture validate, fixture audit.

## Outcomes & Retrospective

- Schemas now give external users and editors a machine-readable contract.
- Runtime Python validator remains stricter for graph cross-reference and policy semantics.
- Patch schema uses references into state schema to avoid duplicated node/edge/frontier definitions.
