---
status: accepted
---

# Score names encode whether the value is expected to change

A score name says how the number behaves under new evidence, not what it measures. `confidence` states the reliability of an observation, which later evidence does not revise: the OCR either read the log correctly or it did not. `prior` states a belief that evidence is expected to move, and the moved value is recorded as `posterior` rather than overwriting the prior, so the revision stays auditable. The name therefore tells a writer which slot a judgment belongs in, and tells a reader whether the number is fixed or provisional.

## Considered Options

- **One generic `probability` field on every node.** Rejected: it hides whether a value is fixed or revisable, mixes both meanings inside one precedence chain, and gives a writer no signal that an unsettled belief belongs in a revisable `prior` rather than a fixed reliability.
- **Naming by node type instead of by behavior** (for example `evidence_score`). Rejected: the same field would mean different things per type with no single rule to remember, and it renames the concept for every new node type.

## Consequences

- Field names can be bound to node types in the schema, so a wrong slot is rejected instead of silently averaging two meanings.
- A conclusion carries no local score: its belief is revisable, so it comes from its premises or from a calibrated `posterior`, never from the fixed-reliability slot.
- A writer who cannot say whether a number is fixed or revisable has not decided what the number is yet.
