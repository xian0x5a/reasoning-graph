# Reasoning Graph Frontier Helpers

## Intent

Derive active search cursor state from compact events and reconstruct path context.

## Behavior

```pseudo
next_event_step(state):
  return one more than highest numeric event step

expansion_signature(item):
  return the expansion identity for active-frontier dedupe:
    node
    sorted active_assumptions
    canonical scope, params, and budget when present
  exclude id, parent, evidence_version, costs, related, and scratch because those do not by themselves change the next expansion

search_cursor(state):
  replay events without mutating state to find initialized frontier, active items, pending pop, stopped state, and selected nodes
  when a supersede event is seen, remove the stale item from active frontier and keep its replacement active if the replacement exists and was not popped

item_view(state, item):
  render compact item context with node, search/base/truth/remaining heuristic costs, related nodes, scratch, assumptions, and evidence version

reconstruct_path(state, item_id):
  follow parent pointers from item to root and return ordered path records
```
