# Evidence node schema

## Goal

Replace `fact` and `contradiction` node types with one `evidence` node type. Keep polarity on edges: `supports` or `contradicts`.

## Constraints

- `constraint` remains separate because it is a requirement/boundary, not observed evidence.
- `test` remains a procedure; performed tests should produce `evidence` nodes.
- `contradicts` edge semantics stay: contradiction penalizes truth cost; it does not delete/disqualify the target.
- Update docs, helper schema, rendering, costs, audit, and tests together.
- Preserve existing CLI commands.
- Pseudocode-first active: update mapped pseudocode before source edits.

## Plan

1. Add/update tests for `evidence` node support and removal of `fact`/`contradiction` node types.
2. Update pseudocode artifacts for affected modules.
3. Patch helper modules:
   - models: node types/classes
   - costs: evidence confidence for contradiction probability
   - render: evidence labels/groups/filters/focus copy
   - audit: terminal expansion checks no longer depend on `contradiction` node type
   - policy/docs wording where needed
4. Patch `SKILL.md` schema guidance and examples.
5. Run validation/test commands and fix drift.

## Progress

- [x] Plan created.
- [x] Tests added for evidence node schema and legacy node rejection.
- [x] Pseudocode artifacts updated before source edits.
- [x] Helper modules patched for evidence nodes.
- [x] `SKILL.md` patched for evidence-first schema.
- [x] Validation/test commands passed.

## Decisions

- Use node type `evidence` for observed/given/verified/source-backed statements, including negative evidence.
- Keep edge type `contradicts`; polarity belongs on relationships.

## Blockers

None.
