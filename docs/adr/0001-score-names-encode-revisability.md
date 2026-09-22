---
status: accepted
---

# Score names encode whether the value is expected to change

A score name distinguishes starting belief, reliability, and calibrated belief. `confidence` states fixed observation or inference reliability. `prior` states a starting belief that graph evidence can update; record a calibrated overall belief as `posterior` rather than overwriting the prior. Both prior and confidence contribute a local factor before graph updates. A posterior overrides those updates and must be explicitly refreshed. These meanings do not require binding a field to a claim's node type.

## Considered Options

- **One generic `probability` field on every node.** Rejected: it hides whether a value is fixed or revisable, mixes both meanings inside one precedence chain, and gives a writer no signal that an unsettled belief belongs in a revisable `prior` rather than a fixed reliability.
- **Naming by node type instead of by behavior** (for example `evidence_score`). Rejected: the same field would mean different things per type with no single rule to remember, and it renames the concept for every new node type.

## Consequences

- Claim types share the named score fields; goals, constraints, and test procedures remain scoreless.
- A conclusion can inherit belief, multiply in additional inference reliability, or use a calibrated posterior. Grounding and double-counting guidance are defined in [ADR 0003](0003-belief-sources.md).
- A writer who cannot say whether a number is fixed or revisable has not decided what the number is yet.
