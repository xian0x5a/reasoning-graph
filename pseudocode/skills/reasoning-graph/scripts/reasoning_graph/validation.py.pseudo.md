# Reasoning Graph Validation

## Intent

Validate graph schema, references, candidate hygiene, and cost metadata before use.

## Behavior

```pseudo
validate_state(state):
  check top-level collections and object ids
  check node types, including evidence instead of legacy fact/contradiction nodes; check edge types, references, statuses, priors, confidence, and answer kinds
  check premise_groups are non-independent premise bundles with id, target, at least two leads_to premises, and joint_probability
  reject overlapping premise_groups for the same target; warn when a grouped target has explicit posterior that overrides graph-derived premise costs
  check candidate solutions connect to accepted goals with `answers` edges only when semantically valid
  reject `answers` edges that do not connect candidate_solution -> goal
  check costs can be computed
  warn about probe-like frontier items without explicit budgets
  return ValidationResult(errors, warnings)
```
