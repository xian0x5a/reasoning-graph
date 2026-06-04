# Reasoning Graph Validation

## Intent

Validate graph schema, references, candidate hygiene, and cost metadata before use.

## Behavior

```pseudo
validate_state(state):
  check top-level collections and object ids
  check node types, edge types, references, statuses, priors, confidence, and answer kinds
  check candidate solutions connect to accepted goals only when semantically valid
  check costs can be computed
  warn about probe-like frontier items without explicit budgets
  return ValidationResult(errors, warnings)
```
