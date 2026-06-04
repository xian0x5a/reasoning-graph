# Reasoning Graph Costs

## Intent

Compute truth/search costs, contradiction penalties, and frontier ordering.

## Behavior

```pseudo
convert probabilities to -ln(probability) costs with bounded validation
read item cost components, including legacy aliases
compute node truth cost from posterior, confidence, prior, or default
for contradicts edges, infer penalty probability from explicit edge strength or source evidence/constraint/test confidence
apply contradiction penalties to target nodes without deleting them
compute each frontier item's local and cumulative truth/search costs from parent links
sort frontier by ascending search cost while keeping all items
```
