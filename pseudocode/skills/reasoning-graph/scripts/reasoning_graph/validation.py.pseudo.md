# Reasoning Graph Validation

## Intent

Validate graph schema, references, candidate hygiene, and cost metadata before use.

## Behavior

```pseudo
validate_state(state):
  check top-level collections and object ids
  check node types, including evidence instead of legacy fact/contradiction nodes; check edge types, references, statuses, priors, confidence, and answer kinds
  check candidate solutions connect to accepted goals with `answers` edges only when semantically valid
  reject `answers` edges that do not connect candidate_solution -> goal
  check costs can be computed
  warn about probe-like frontier items without explicit budgets
  return ValidationResult(errors, warnings)
```
