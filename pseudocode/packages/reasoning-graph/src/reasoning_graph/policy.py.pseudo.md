# Reasoning Graph Policy Helpers

## Intent

Centralize goal, candidate, and stop-policy predicates used by validation, audit, and reports.

## Behavior

```pseudo
identify accepted, preferred, and epistemic goals
resolve candidate-to-goal targets from `answers` edges
classify which answer kinds each goal can accept
find selected, pruned, viable, and salient clue-family candidates
rank report candidates using belief, incoming contradicts-edge penalties, selected status, and modern search_cost only
recognize stop reasons that claim exhaustion
```
