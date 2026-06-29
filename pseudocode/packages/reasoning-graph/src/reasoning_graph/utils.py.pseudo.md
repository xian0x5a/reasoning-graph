# Reasoning Graph Utilities

## Intent

Provide small shared coercion helpers.

## Behavior

```pseudo
as_string_list(value):
  return list of strings when value is a list, otherwise empty list

finite_float(value):
  convert to finite float when possible, otherwise return None
```
