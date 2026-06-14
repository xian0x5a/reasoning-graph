# Reasoning Graph Models

## Intent

Define shared constants and validation result data used across helper modules.

## Behavior

```pseudo
provide canonical node types, including evidence instead of legacy fact/contradiction node types; provide edge types, including `answers` for candidate_solution-to-goal links; provide event actions including `supersede` for active frontier dedupe, stop outcomes, statuses, answer kinds, markers, cost component names, and renderer class mapping
ValidationResult stores errors and warnings
ValidationResult.ok is true only when errors is empty
```
