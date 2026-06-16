# Tighten JSON Schemas Against Legacy Fields

## Goal

Make the machine-readable schemas describe the modern reasoning-graph interchange contract instead of documenting deprecated/legacy aliases.

## Decision

Do not replace Python validation with JSON Schema. Use both layers:

- JSON Schema: structural shape, primitive types, enums, and explicit rejection of known legacy aliases.
- Python validator/audit: cross-reference checks, graph topology, costs, policy semantics, frontier/event replay, and stop-review logic.

`rg.py validate` remains semantic validation because the project has no declared runtime dependency on `jsonschema`, and JSON Schema cannot express many graph invariants.

## Changes

- Removed deprecated state schema fields like top-level `solutions`, edge `label`, frontier `path_cost`, and event `solution` action.
- Removed deprecated patch aliases like `add_*_objects`, `solution`, `solution_node`, `no_reopen_reason`, and `stop`.
- Added schema `not` guards so known legacy aliases are rejected even with extensible objects.
- Added tests asserting schemas contain no `deprecated` metadata and reject known legacy fields.
- Documented schema role in README.

## Validation

- `python -m unittest discover -s tests/scripts` → 58 tests passed
- `python -m json.tool skills/reasoning-graph/schemas/state.schema.json`
- `python -m json.tool skills/reasoning-graph/schemas/patch.schema.json`
- fixture validate/audit/stop-review OK
