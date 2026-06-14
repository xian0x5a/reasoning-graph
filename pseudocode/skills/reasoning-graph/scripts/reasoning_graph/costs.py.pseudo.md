# Reasoning Graph Costs

## Intent

Compute truth/search costs, contradiction penalties, and frontier ordering.

## Behavior

```pseudo
convert probabilities to -ln(probability) costs with bounded validation
read item cost components, including legacy aliases
compute node truth cost from posterior, confidence, prior, or default
reject cycles in the raw leads_to truth dependency graph before applying premise group cost replacement
for each target, treat plain incoming leads_to premises as independent required premises
when premise_groups are present, replace grouped member premise costs with that group's joint_probability cost
for supports/contradicts edges with likelihood updates, update target belief in odds space
compute each frontier item's local and cumulative truth/search costs from parent links
sort frontier by ascending search cost while keeping all items
```
