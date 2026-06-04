# Reasoning Graph State Helpers

## Intent

Load, save, and index reasoning graph JSON state.

## Behavior

```pseudo
load_state(path):
  if path is '-': read JSON from stdin
  otherwise read JSON file

dump_state(state, output_path, in_place_source):
  serialize stable pretty JSON
  write to explicit output, in-place source, or stdout

by_id(items, label):
  build id -> object mapping
  reject missing/duplicate ids

node_label(node):
  return compact id/type/text label for display
```
