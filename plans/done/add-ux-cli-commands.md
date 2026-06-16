# Add Reasoning Graph UX CLI Commands

## Goal

Add low-friction CLI entry points so users/agents can bootstrap and inspect reasoning graph states without hand-authoring JSON from scratch.

## Intention

Reduce adoption friction after docs split. `template`, `init`, and `doctor` should provide safe, simple affordances while existing strict validator/audit remain canonical.

## Scope & Constraints

- Source changes follow pseudocode-first for `cli.py`.
- Avoid new runtime dependencies.
- Keep existing commands backward compatible.
- Commands should be conservative and generate valid states.

## Work Plan

1. Add pseudocode for new commands.
2. Implement:
   - `template minimal|strict|benchmark` emits starter JSON state.
   - `init --goal TEXT [-o PATH] [--strict]` emits starter state with one goal and optional strict policies.
   - `doctor STATE` runs validate, costs, frontier cursor summary, optional audit if events exist, and returns nonzero on validation/audit errors.
3. Add unit tests for command outputs and doctor behavior.
4. Run full tests and fixture validate/audit.

## Validation

- `python -m unittest discover -s tests/scripts`
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`

## Progress

- Started after schema commit `e60411b`.
- Updated CLI pseudocode for `template`, `init`, and `doctor`.
- Implemented starter state profiles: `minimal`, `strict`, `benchmark`.
- Implemented `doctor` validation/cost/frontier/audit health summary.
- Added CLI tests for starter output, validation, and doctor success/failure.
- Updated README, `SKILL.md`, and driver reference command lists.
- Validation passed: py_compile, unittest suite, fixture validate/audit/doctor, generated template/init validate.

## Outcomes & Retrospective

- Users can now bootstrap valid state JSON without hand-authoring all fields.
- `doctor` gives a single safe health command before deeper graph work or final output.
- Existing commands remain backward compatible.
