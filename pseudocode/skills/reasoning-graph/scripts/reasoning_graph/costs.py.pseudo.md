# Reasoning Graph Costs

## Intent

Compute truth/search costs, contradiction penalties, and frontier ordering.

## Behavior

```pseudo
validate numeric probabilities through one required-probability helper, then convert to -ln(probability) costs
expose shared node probability field lists for truth-cost precedence and display order
read item cost components, including legacy aliases
compute node truth cost from shared precedence: posterior, confidence, probability, prior, or default
reject cycles in the raw leads_to truth dependency graph before applying factor cost replacement
for each target, treat plain incoming leads_to premises as independent required premises
when premise_groups or leads_to factors are present, replace grouped member premise costs with the group's joint_probability cost
when supports/contradicts factors are present, replace grouped member likelihood updates with the factor's conditional likelihood ratio
for ungrouped supports/contradicts edges with likelihood updates, update target belief in odds space
compute each frontier item's local truth/work base search cost
read optional top-level estimated_remaining_cost as a non-negative heuristic only, not as truth or work cost
reject misplaced estimated_remaining_cost under cost_components so user intent is not silently ignored
validate optional state.search_policy as an object and read state.search_policy.estimated_remaining_weight, defaulting to 1.0, to scale the remaining-cost heuristic
set search_cost to base_search_cost plus weighted estimated_remaining_cost; keep base_search_cost and heuristic_cost visible for auditability
sort frontier by ascending search cost while keeping all items
```
