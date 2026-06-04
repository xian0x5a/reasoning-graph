# Reasoning Graph Frontier Helpers

## Intent

Derive active search cursor state from compact events and reconstruct path context.

## Behavior

```pseudo
next_event_step(state):
  return one more than highest numeric event step

search_cursor(state):
  replay events to find initialized frontier, active items, pending pop, stopped state, and selected nodes

item_view(state, item):
  render compact item context with node, cost, related nodes, scratch, assumptions, and evidence version

reconstruct_path(state, item_id):
  follow parent pointers from item to root and return ordered path records
```
