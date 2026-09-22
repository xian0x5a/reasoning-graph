# Reasoning Graph Costs

## Intent

Compute truth/search costs, contradiction penalties, and frontier ordering.

## Behavior

```pseudo
validate numeric probabilities through one required-probability helper, then convert to -ln(probability) costs
expose the shared node score field list and truth-cost precedence
read item cost components, including legacy aliases
compute local truth cost from prior, or use an explicit posterior override; reject obsolete scores and authored belief inputs
reject cycles in the raw leads_to truth dependency graph before applying factor cost replacement
for each target, treat plain incoming leads_to premises as independent required premises
when leads_to factors are present, replace grouped member premise costs with the factor's joint_probability cost
when supports/contradicts factors are present, replace grouped member likelihood updates with the factor's conditional likelihood ratio
for ungrouped supports/contradicts edges with likelihood updates, update target belief in odds space
compute each frontier item's local truth/work base search cost
reject frontier items that contain legacy path_cost; users must provide modern cost_components/search_cost state instead of relying on migration
read optional top-level estimated_remaining_cost as a non-negative heuristic only, not as truth or work cost
reject misplaced estimated_remaining_cost under cost_components so user intent is not silently ignored
validate optional state.search_policy as an object and read state.search_policy.estimated_remaining_weight, defaulting to 1.0, to scale the remaining-cost heuristic
set search_cost to base_search_cost plus weighted estimated_remaining_cost; keep base_search_cost and heuristic_cost visible for auditability
sort frontier by ascending search_cost while keeping all items
```

## Required node scores and edge reasoning

Share a compact score label between Mermaid and offline SVG renderers using posterior/prior precedence; keep the field name so an authored override stays distinguishable from the local input. Return computed effective belief without writing it into node scores, and render no score line for scoreless objectives/actions.
