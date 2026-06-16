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
  doctor command validates a state, attempts cost/frontier summary only after validation passes, audits when events exist, prints concise diagnostics, and returns nonzero on validation or audit errors
  call validation, audit, cost, frontier, render, or event helpers
  expand patches can append nodes, edges, frontier items, upsert premise_groups through update_premise_groups, and upsert factors through update_factors, then record matching event ids
  use one shared frontier insertion chooser for init and expand dedupe
  frontier and next text output shows estimated remaining heuristic details when present
  before creating an init event, recompute current costs from latest graph evidence and include only one frontier item per expansion_signature
  before appending new frontier items, recompute current costs from latest graph evidence and group active plus new frontier candidates by expansion_signature
  for each duplicate expansion_signature, keep the lowest-cost item; ties prefer the existing/earlier item
  append only kept new frontier items and emit supersede events for active existing items replaced by a lower-cost duplicate
  preserve existing output, mutation, and error behavior
```
