# Reasoning Graph Models

## Intent

Define shared constants and validation result data used across helper modules.

## Behavior

```pseudo
provide canonical node types, edge types, event actions, stop outcomes, statuses, answer kinds, markers, cost component names, and renderer class mapping
ValidationResult stores errors and warnings
ValidationResult.ok is true only when errors is empty
```
