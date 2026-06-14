# Reasoning Graph Audit

## Intent

Audit driver events and stop policy after graph search has been recorded.

## Behavior

```pseudo
audit_state(state):
  run validation first
  replay init/pop/expand/select/stop events
  verify frontier pops are coherent and lowest cost
  verify expansions and selections match pending items and graph topology
  verify supersede events reference same-signature active items, require the replacement to have strictly lower current cost than the retired item, and remove the stale item from the active frontier
  verify expansion update_premise_groups and update_factors reference existing ids and treat their targets as numeric belief updates
  treat candidate additions and contradicts-edge penalties as terminal/penalizing expansion signals
  verify stop events include valid outcomes and satisfy stop policy
  report errors/warnings without mutating state
```
