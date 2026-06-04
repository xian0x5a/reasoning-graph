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
  verify stop events include valid outcomes and satisfy stop policy
  report errors/warnings without mutating state
```
