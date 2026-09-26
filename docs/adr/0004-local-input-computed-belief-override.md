---
status: accepted
supersedes: 0001-score-names-encode-revisability.md
---

# Separate local input, computed belief, and explicit override

`confidence` and `prior` had the same computational role: a local probability factor before premise propagation and likelihood updates. Neither stored value was rewritten, and supplying both silently preferred confidence. Merge them into one optional `prior` rather than preserving a fixed-versus-revisable distinction the engine did not implement.

| Concept | Contract |
| --- | --- |
| `prior` | Authored local starting-probability factor, including observation or inference reliability |
| Computed `belief` | Output from the current graph; never written back into node scores |
| Explicit `posterior` | Authored calibrated overall value, overriding this node's prior and incoming calculations |

A premise-backed claim can omit its prior and inherit belief. Adding a local prior represents additional uncertainty, not the already-aggregated conclusion: premise 0.8 times inference prior 0.9 gives 0.72, not a second factor of 0.72. Grounding and certainty remain governed by [ADR 0003](0003-belief-sources.md).

A stored posterior remains fixed until explicitly refreshed or removed. Downstream nodes can inherit it and perform their own updates; removing the override resumes computation from current inputs. The engine trusts the supplied calibration rather than verifying it.

Reject `confidence` and the previously removed `probability` on nodes, including when a valid prior or posterior is also present. Reject authored node `belief` because it is output-only. ([ADR 0007](0007-state-stores-computed-belief.md) amends this: the CLI now writes `belief` on claims, and patches still reject it.) Do not add aliases, fallback precedence, or automatic conversion. Use the [cost model](../../skills/reasoning-graph/docs/cost-model.md) for operational examples.
