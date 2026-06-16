# Package Reasoning Graph as Real Python Project

## Goal

Move the `reasoning_graph` Python package to standard `src/` layout, add `pyproject.toml`, declare `jsonschema`, and make `rg.py validate` run JSON Schema before semantic validation.

## Intent

Use one authoritative validation command with two layers:

1. JSON Schema contract for structure, enums, primitive types, and legacy-field rejection.
2. Python semantic validator for graph topology, references, costs, policy semantics, and audit prerequisites.

## Scope

- Move `skills/reasoning-graph/scripts/reasoning_graph/` to `src/reasoning_graph/`.
- Move matching pseudocode to `pseudocode/src/reasoning_graph/`.
- Keep `skills/reasoning-graph/scripts/rg.py` as compatibility wrapper.
- Add `pyproject.toml` with package metadata, `jsonschema` dependency, and `rg` console script.
- Update tests to import from `src` and still test wrapper path.
- Add schema validation module and fuse schema-first checks into `rg.py validate`, `doctor`, `audit`, and `stop-review` via combined validator.
- Update docs for installed CLI plus wrapper path.

## Constraints

- Preserve existing `./scripts/rg.py` skill usage.
- No broad behavior changes beyond schema-first validation.
- Follow pseudocode-first for behavior changes.
- Use `git mv` for tracked file moves.

## Validation

- `uv run python -m unittest discover -s tests/scripts`
- `uv run rg validate tests/reasoning-graph-strict-good.json`
- `uv run rg audit tests/reasoning-graph-strict-good.json`
- `uv run rg stop-review tests/reasoning-graph-strict-good.json`
- `uv run python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`

## Progress

- Started after schema-tightening commit `8720041`.
- Moved package source to `src/reasoning_graph/`.
- Moved mapped pseudocode to `pseudocode/src/reasoning_graph/`.
- Moved schemas into package data under `src/reasoning_graph/schemas/`.
- Added `pyproject.toml`, `uv.lock`, `jsonschema` dependency, and `rg` console script.
- Kept `skills/reasoning-graph/scripts/rg.py` as compatibility wrapper that imports from `src`.
- Added packaged schema validation module and fused schema errors into `validate_state()`.
- Added patch schema validation before `expand` applies patches.
- Stopped emitting modern-output `path_cost`; legacy input fallback remains readable.
- Updated tests and docs for package layout and schema-first validation.
- Validation passed: `python` and `uv run` unittest suites, `uv run rg` validate/audit/stop-review, wrapper validate, py_compile, JSON schema parse.

## Outcomes & Retrospective

- `rg.py validate` is now authoritative for both schema contract and semantic graph checks.
- Installed CLI path (`uv run rg`) and skill wrapper path both work.
- Package data makes schemas available after installation.
- `rg` command name can collide with ripgrep outside the uv environment, so tests invoke `uv run rg` for console-script coverage.
