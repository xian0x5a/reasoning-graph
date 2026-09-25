---
status: accepted
---

# Node types name observation and hypothesis roles

## Context

[ADR 0003](0003-belief-sources.md) made the belief contract type-blind: every claim node may carry a local prior, a posterior override, `leads_to` premises, or a joint factor. After that decision `assumption` and `derived` shared every mechanic. The only type-specific code left was a validation rule rejecting `assumption -> goal` edges, the set of node types allowed as test results, and two render clusters.

The names still encoded the retired contract. `derived` read as "already established from premises", so an intermediate claim asserted before its proof, the lemma pattern, looked wrong as a derived node. `assumption` read as "taken as given", so a compound claim with its own sub-search looked wrong as an assumption. The docs steered agents into recording such a claim twice: an assumption while open, then a derived node once proved, with every downstream edge needing rewiring or double counting.

`evidence` had a different problem. The most common trace failure was an interpretation recorded as evidence, for example "Evidence: the encoding is base64". The name did not push the agent to record what was seen.

Adding a `lemma` type beside the existing two was considered and rejected: three names for one belief contract multiplies the classification ambiguity. Borrowing the wider mathematical vocabulary (theorem, proposition, corollary, axiom, conjecture, remark) was rejected because those terms rank statements by importance rather than by structural role, and the tool is abductive and multi-domain. `claim` as the merged name was rejected because ADR 0003 and the cost model already use "claim" as the umbrella for every belief-bearing node.

## Decision

Merge `assumption` and `derived` into one node type, `hypothesis`, and rename `evidence` to `observation`. The node types are `goal`, `observation`, `constraint`, `hypothesis`, `test`, and `candidate_solution`. The old names are removed without aliases or migration code.

Two rules change with the merge:

- A test result is an `observation` only. A conclusion drawn from a result is a separate `hypothesis` linked by `leads_to` from the observation.
- No edge may run from a `hypothesis` to a `goal`. Claims reach goals only through `candidate_solution --answers--> goal`.

Role guidance moves into the skill docs rather than the type system. Competing interpretations are sibling hypotheses: atomic, each with its own frontier item, re-ranked against each other. An intermediate step on a route toward the goal is a hypothesis with its own sub-search and may be compound. A blocker is a hypothesis backed by observations. A lemma-shaped claim is one node for its whole life: a prior while open, `leads_to` premises once proved.

The statistical word "evidence" remains in likelihood formulas such as P(evidence | target true). It names a quantity, not a node type.

## Consequences

- The belief contract, cost engine, frontier ranking, stop gates, and audit semantics are unchanged. ADR 0003 and ADR 0004 remain the score contract; their references to evidence, assumption, and derived nodes are historical names for observation and hypothesis nodes.
- Fixtures that recorded a `derived` test result retype that node as `observation`.
- Rendering shows one hypothesis cluster instead of separate assumption and inference clusters.
- Proof-shaped tasks map their vocabulary onto the type set: theorem is a `goal`; an axiom or given is an `observation` with prior 1.0, or a `constraint`; lemma, proposition, corollary, and conjecture are hypotheses; a proof is a `candidate_solution` with `exact_method`; a remark is report text. The table lives in the skill's goals reference.
- State files written before this change fail validation on the old type names and are rewritten by hand or regenerated.
