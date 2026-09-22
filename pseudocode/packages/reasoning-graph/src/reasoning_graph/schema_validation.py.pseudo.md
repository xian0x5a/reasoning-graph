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

Allow prior as the local probability input and posterior as an explicit calibrated override on claim nodes; leave goals, constraints, and tests scoreless. Reject confidence, probability, and output-only belief as node inputs. Describe each input at its schema property. Full-state validation checks inherited belief sources after patches are merged. Require nonblank edge reasoning using standard string constraints; sentence count remains authoring guidance, not a custom validation format.
