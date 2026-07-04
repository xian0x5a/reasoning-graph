# Reasoning Graph Validation

## Intent

Validate graph schema, references, candidate hygiene, and cost metadata before use.

## Behavior

```pseudo
validate_state(state):
  collect JSON Schema contract errors first
  continue semantic validation so one command reports both schema and graph-specific diagnostics
  check top-level collections and object ids
  check node types, including evidence instead of legacy fact/contradiction nodes; check edge types, references, priors and other probability fields through shared numeric validation, and answer kinds
  check factors are virtual numeric relation groups with id, relation, target, at least two inputs, and relation-appropriate aggregation
  reject top-level premise_groups and patch/event update_premise_groups through schemas; reject overlapping leads_to/supports/contradicts factors for the same target and relation; warn when a grouped target has explicit posterior that overrides graph-derived costs
  check candidate solutions connect to accepted goals with `answers` edges only when semantically valid
  reject `answers` edges that do not connect candidate_solution -> goal
  check search_policy numeric fields, including non-negative estimated_remaining_weight and positive integer max_probe_concurrency when present
  check costs can be computed
  warn about probe-like frontier items without explicit budgets
  return ValidationResult(errors, warnings)
```
