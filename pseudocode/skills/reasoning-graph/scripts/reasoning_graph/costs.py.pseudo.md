# Reasoning Graph Costs

## Intent

Compute truth/search costs, contradiction penalties, and frontier ordering.

## Behavior

```pseudo
convert probabilities to -ln(probability) costs with bounded validation
read item cost components, including legacy aliases
compute node truth cost from posterior, confidence, prior, or default
reject cycles in the raw leads_to truth dependency graph before applying factor cost replacement
for each target, treat plain incoming leads_to premises as independent required premises
when premise_groups or leads_to factors are present, replace grouped member premise costs with the group's joint_probability cost
when supports/contradicts factors are present, replace grouped member likelihood updates with the factor's conditional likelihood ratio
for ungrouped supports/contradicts edges with likelihood updates, update target belief in odds space
compute each frontier item's local and cumulative truth/search costs from parent links
sort frontier by ascending search cost while keeping all items
```
