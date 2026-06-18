# Reasoning Graph CLI Module

## Intent

Parse command-line arguments and dispatch each subcommand to the appropriate helper behavior.

## Behavior

```pseudo
main(argv):
  build parser with existing subcommands and options
  parse args
  call the selected command handler
  return handler exit code

command handlers:
  load state when needed
  template command emits starter state JSON for minimal, strict, or benchmark profiles
  init command emits starter state JSON from a goal string, with optional strict policies
  seed command applies an initial ledger/frontier patch only before first pop/init events, rejects non-root frontier parent refs, recomputes costs, validates state, and writes the seeded state without appending driver events
  doctor command validates a state, attempts cost/frontier summary only after validation passes, audits when events exist, prints concise diagnostics, and returns nonzero on validation or audit errors
  stop-review command validates stopped state, audits event traces when present, checks selected candidate presence/viability, optionally compares final draft against selected candidate ids/text, prints YAML-like verdict, and returns nonzero on required fixes
  call validation, audit, cost, frontier, render, or event helpers
  assign command records the pending popped item as async in-flight probe work, enforcing max concurrency from CLI or search_policy before allowing later pops
  stop command is the only terminal command: for candidate-bearing outcomes it ranks the current best viable candidate_solution before writing the stop event; for non-candidate outcomes it writes only the stop event
  stop and patch stop paths reject stop while a pending popped item or assigned in-flight probe remains unresolved
  expand command validates patch JSON against packaged patch schema before applying it
  expand may target the pending popped item or an in-flight assigned item so async probe results can be merged out of order
  expand patches can append nodes, edges, frontier items, upsert premise_groups through update_premise_groups, and upsert factors through update_factors, then record matching event ids
  use one shared frontier insertion chooser for seed/init and expand dedupe
  frontier, next, path, pop, and duplicate-selection output uses modern search_cost only; legacy path_cost is never read as a fallback
  frontier and next text output shows estimated remaining heuristic details when present
  before creating an init event, recompute current costs from latest graph evidence and include only one frontier item per expansion_signature
  before appending new frontier items, recompute current costs from latest graph evidence and group active plus new frontier candidates by expansion_signature
  for each duplicate expansion_signature, keep the lowest-cost item; ties prefer the existing/earlier item
  append only kept new frontier items and emit supersede events for active existing items replaced by a lower-cost duplicate
  preserve existing output, mutation, and error behavior
```
