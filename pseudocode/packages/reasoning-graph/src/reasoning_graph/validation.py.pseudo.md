# Reasoning Graph Validation

## Intent

Validate graph schema, references, candidate hygiene, and cost metadata before use.

## Behavior

```pseudo
validate_state(state):
  collect JSON Schema contract errors first
  continue semantic validation so one command reports both schema and graph-specific diagnostics
  check top-level collections and object ids
  check node types, including evidence instead of legacy fact/contradiction nodes; check edge types, references, statuses, priors and other probability fields through shared numeric validation, and answer kinds
  check premise_groups are legacy non-independent premise bundles with id, target, at least two leads_to premises, and joint_probability
  check factors are virtual numeric relation groups with id, relation, target, at least two inputs, and relation-appropriate aggregation
  reject overlapping premise_groups/leads_to factors for the same target; reject overlapping supports/contradicts factors for the same target and relation; warn when a grouped target has explicit posterior that overrides graph-derived costs
  check candidate solutions connect to accepted goals with `answers` edges only when semantically valid
  reject `answers` edges that do not connect candidate_solution -> goal
  check search_policy numeric fields, including non-negative estimated_remaining_weight and positive integer max_probe_concurrency when present
  check costs can be computed
  warn about probe-like frontier items without explicit budgets
  return ValidationResult(errors, warnings)
```
