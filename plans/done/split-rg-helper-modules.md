# Split rg helper into modules

## Goal

Refactor `skills/reasoning-graph/scripts/rg.py` from one long script into a normal importable Python package while preserving the existing `./scripts/rg.py` command and behavior.

## Constraints

- No behavior changes in this refactor.
- Keep helper runnable without install or `PYTHONPATH` through the existing `rg.py` shim.
- Use `scripts/reasoning_graph/` as the package namespace.
- Preserve validation commands:
  - `python -m py_compile skills/reasoning-graph/scripts/rg.py`
  - `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
  - `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`
- Pseudocode-first active: create/update pseudocode artifacts before source edits.

## Plan

1. Backfill pseudocode for current `rg.py` behavior and the no-behavior-change module split.
2. Create `scripts/reasoning_graph/` package.
3. Move code by responsibility:
   - constants/result types
   - state/util/cost/frontier helpers
   - validation/audit
   - rendering
   - CLI command dispatch
4. Replace `rg.py` with thin shim importing `reasoning_graph.cli.main`.
5. Run validation commands and inspect diffs.

## Progress

- [x] Plan created.
- [x] Pseudocode artifacts created.
- [x] Modules created.
- [x] Shim installed.
- [x] Validation passed.

## Decisions

- Package name: `reasoning_graph`, not `rg`, to avoid `rg.py` plus `rg/` ambiguity.
- Keep `rg.py` path stable for skill docs and existing usage.

## Blockers

None.
