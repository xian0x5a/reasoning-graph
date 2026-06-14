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
  call validation, audit, cost, frontier, render, or event helpers
  expand patches can append nodes, edges, frontier items, and upsert premise_groups through update_premise_groups, then record matching event ids
  preserve existing output, mutation, and error behavior
```
