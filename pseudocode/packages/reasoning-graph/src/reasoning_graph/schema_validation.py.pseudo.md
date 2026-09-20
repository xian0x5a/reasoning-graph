# Reasoning Graph Schema Validation

## Intent

Validate JSON state and patch documents against packaged JSON Schemas before semantic graph validation.

## Behavior

```pseudo
schema_validation_errors(document, schema_name):
  load packaged schema by name from reasoning_graph/schemas
  create Draft 2020-12 validator
  resolve local refs between state and patch schemas
  collect all validation errors sorted by path
  format each error with json path and validator message
  return formatted error strings

state_schema_errors(state):
  return schema_validation_errors(state, "state.schema.json")

patch_schema_errors(patch):
  return schema_validation_errors(patch, "patch.schema.json")
```

## Required node scores and edge reasoning

Require type-bound node scores: prior or posterior on assumptions and candidate solutions, confidence on evidence, no local score on derived nodes (posterior only, once calibrated), none on goals, constraints, and tests; reject the removed generic probability field. Require edge reasoning as nonblank text with one to five sentences. Register a reasoning-sentences format checker for both state and patch validation; split on sentence punctuation followed by whitespace, allowing decimal numbers and a final sentence without punctuation. Reject punctuation-only text.
