# Reasoning Graph Helper CLI

## Intent

Provide a no-dependency command-line helper for validating, auditing, costing, driving, and rendering reasoning-graph JSON state files.

## Behavior

```pseudo
command rg.py(args):
  parse subcommand and options
  load JSON state from file or stdin when command needs state

  if subcommand is validate:
    check graph schema, references, node/edge types, candidate hygiene, cost metadata, and policy-related warnings
    print errors/warnings
    return nonzero if validation errors exist

  if subcommand is costs:
    compute truth/search costs from priors, confidence, explicit cost components, parent links, and contradiction penalties
    write updated state to output, in-place file, or stdout

  if subcommand is audit:
    validate state first
    audit compact driver events for coherent frontier/search trace and stop-policy consistency
    print errors/warnings
    return nonzero if audit errors exist

  if subcommand is sort:
    compute costs and sort frontier by search cost without dropping items
    write updated state

  if subcommand is frontier:
    derive active frontier from events
    print active items ordered by search cost

  if subcommand is next:
    derive active frontier and choose the lowest-cost item
    print item context and reconstructed path
    if --pop:
      reject when previous pop is still pending expansion/selection/stop
      append init event if needed
      append pop event for chosen item
      write updated state

  if subcommand is expand:
    require a pending popped item or explicit item
    read expansion patch
    append new nodes, edges, and frontier items
    fill missing child parent with expanded item
    append expand event
    validate resulting state before writing

  if subcommand is select:
    require selected node to be a candidate_solution
    append select event for pending item
    write updated state

  if subcommand is stop:
    require non-empty reason and valid outcome
    append stop event
    write updated state

  if subcommand is path:
    reconstruct parent-pointer path for a frontier item
    print text or JSON

  if subcommand is mermaid:
    render Mermaid graph from state, optionally curated by presentation metadata

  if subcommand is html:
    validate state, render Mermaid audit/presentation graphs, candidate tables, node details, and report HTML
    write HTML to requested path or stdout
```
