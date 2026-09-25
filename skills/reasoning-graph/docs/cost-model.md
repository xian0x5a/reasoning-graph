# Reasoning Graph Cost Model

Local probability inputs, computed belief, calibrated overrides, search costs, and correlated evidence.

## Local input, computed belief, and explicit override

| concept | role |
| --- | --- |
| `prior` | Optional local starting-probability input, including observation or inference reliability |
| Computed `belief` | Output after premise propagation and likelihood updates, reported from effective truth cost |
| Explicit `posterior` | Authored, already-calibrated overall value that overrides this node's calculation |

Claim nodes (`observation`, `hypothesis`, and `candidate_solution`) accept `prior` and `posterior`. Each claim requires a **belief source**: a local prior, an explicit posterior, a source inherited through `leads_to` premises, or a calibrated joint-probability factor. A chain of unscored claims, a scoreless goal/constraint/test, or likelihood updates alone cannot supply a starting belief. `validate`, `seed`, and `expand` check grounding on the complete graph; patch schemas permit omitted scores because their premises may already exist in the state.

Authored probabilities are in `(0, 1]`. Zero is excluded because cost is `-ln(P)`; record impossibility in the claim or status instead of inventing a small number. Use coarse values and avoid fake precision. Removed node fields `confidence` and `probability` are rejected, not converted. `belief` is output-only and rejected as an authored node field.

A local `prior` multiplies premise belief. **Omit it when it merely repeats uncertainty already represented by the premises.** A hypothesis at `0.6` leading to an unscored candidate gives candidate belief `0.6`, not `0.3`; adding a candidate `prior: 0.5` represents additional uncertainty. On a premise-backed node, `prior` is a local factor, not an estimate of the already-aggregated conclusion.

For a soft inference, observation `prior: 0.8` times inference `prior: 0.9` gives base belief `0.72`. Alternatively, put inference validity in a separate hypothesis with `prior: 0.9` and a `leads_to` edge when it deserves independent scrutiny. Use one representation, not both. Omitting the local prior adds no extra uncertainty; validation checks grounding, not logical entailment. Keep derivation edges to explain conclusions, even when a local prior alone satisfies validation.

The engine computes effective belief from this base and likelihood updates; it never writes that result into a node's `prior`, `posterior`, or `belief`. For example, base `0.72` and supporting ratio `2` give computed belief `36/43`, while the authored priors remain `0.8` and `0.9`. Changing the premises or likelihoods changes the next computed result.

A stored `posterior` is different: it overrides this node's prior and incoming premise, factor, and likelihood calculations until explicitly refreshed or removed. It is trusted as calibrated, not verified by the engine. A node with `prior: 0.9` and `posterior: 0.7` has effective belief `0.7`; downstream nodes can inherit that value and apply their own priors and updates. Removing the override resumes computation from the current inputs. Preserve the local prior for auditing; never substitute search costs for belief. Graph labels and candidate tables show effective belief; node details distinguish that result from the local prior and any posterior override. See [belief display](rendering.md#belief-display).

Mutually exclusive sibling hypotheses should form a local distribution summing to `1.0`; independent hypotheses need not. A `test` is a procedure, not a claim: record its outcome as a separate `observation` node. Goals, constraints, and tests carry no score.

### Certainty is not an unknown score

`1.0` means certain, never "no score specified". For an unresolved hypothesis, state a justified estimate; `prior: 0.5` is a deliberately neutral start, and a node that carries no belief at all carries no score instead of a placeholder.

A base belief of `1.0`, whether local or inherited from certain premises or a calibrated joint factor, stays `1.0` under finite likelihood ratios. A neutral `prior: 0.5` with supporting ratio `2` gives belief `2/3`; contradicting ratio `0.1` gives `1/11`.

The cost engine tracks belief sources separately from their numerical cost. An ungrounded claim uses neutral `0.5` before likelihood updates even without validation, rather than silently reporting certainty; the complete state is still rejected. Scoreless objectives/actions retain zero truth penalty, which does not mean they are true.

### Required edge reasoning

Every edge requires nonblank `reasoning` explaining the directed relationship, including `requires`, `prompts`, `answers`, and factor member edges. Aim for one to five sentences. Repeating the edge type is not an explanation, and a factor's `reason` does not replace member-edge reasoning.

```json
{"id": "E1-D1", "from": "E1", "to": "D1", "type": "leads_to", "reasoning": "The deployment timestamp is earlier than the first failing request, so deployment preceded the outage."}
```

State and patch schemas enforce nonblank text with standard string constraints; no custom format checker is needed. Sentence count is guidance, not a rejection rule: abbreviations and punctuation are not reliable sentence boundaries. Explain the relationship meaningfully; validation cannot judge prose quality.

Use `search_cost` to rank the next frontier action. Lower cost means explore earlier. Valid current states use `search_cost`; schemas and runtime cost commands reject legacy `path_cost`. It is not auto-migrated; replace old frontier cost fields with `search_cost`/`cost_components` before running `validate`, `costs`, `sort`, or `next`.

Recommended hybrid cost model:

```txt
truth_cost = -ln(P(claim true))
base_truth_cost(target) = local_truth_cost(target) + sum(effective_truth_cost(ungrouped premises via leads_to)) + sum(-ln(leads_to factor joint_probability))
base_odds = P_base / (1 - P_base)
updated_odds = base_odds * product(ungrouped supports/contradicts likelihood ratios) * product(supports/contradicts factor likelihood ratios)
effective_truth_cost = -ln(updated_odds / (1 + updated_odds))

base_search_cost =
  effective_truth_cost(current node)
+ local_verification_cost
+ local_effort_budget
+ local_reasoning_complexity_cost
+ local_constraint_tension_cost

search_cost =
  base_search_cost
+ search_policy.estimated_remaining_weight * estimated_remaining_cost
```

`truth_cost` measures current plausibility from the graph's probability model. `base_search_cost` measures local remaining effort/risk. Optional top-level `estimated_remaining_cost` is a heuristic estimate of remaining work: unmet criteria, missing observations, unresolved constraints, confidence gap, dependency depth, or similar effort. It is not truth cost and should stay outside `cost_components`. `search_policy.estimated_remaining_weight` defaults to `1.0`; set it lower when rough heuristics should guide order without dominating local cost.

`search_cost` is frontier priority. Past work is sunk and does not accumulate into frontier priority. Priority queue order is by lowest `search_cost`, not highest belief alone. Ties break by frontier item id.

Two accumulation axes are easy to conflate. Belief accumulates through the claim graph: `leads_to` premises multiply into the target node's belief, so premises `0.8` and `0.9` give `0.72` and cost `0.2231 + 0.1054`. Search depth does not accumulate: an item's priority reflects its own belief and remaining work, never the route taken to reach it, so items on the same node price identically at any depth.

Exact math is optional. Rough costs are acceptable when they preserve ordering and make the search better.

### Bounded Effort / Probe Priority

Brute-force, broad probing, sweeps, enumeration, or high-volume checking are not inherently low-cost just because a script is easy to run. Their search cost must include the committed effort budget.

A probe/brute-force branch may have low `search_cost` only when it is:

- tightly bounded (`max_attempts`, `max_seconds`, `max_items`, or equivalent),
- a cheap discriminator for a specific clue-based hypothesis,
- stopped as soon as its budget or discriminator condition is reached,
- and recorded with `cost_components.effort_budget` plus `budget` metadata.

Example:

```json
{
  "id": "Q7",
  "node": "H7",
  "cost_components": {
    "truth": "auto",
    "verification": 0.2,
    "effort_budget": 0.3,
    "reasoning_complexity": 0.1,
    "constraint_tension": 0.0
  },
  "estimated_remaining_cost": 0.4,
  "budget": {"max_attempts": 20, "max_seconds": 30, "stop_after": "first discriminating result"}
}
```

If the branch means broad brute force, open-ended enumeration, or spending most of the run budget, assign high `effort_budget` so frontier priority explores authoritative clues and cheap source/semantic checks first. Validator warns when a probe-like frontier item lacks both `effort_budget` and explicit `budget` metadata.

### Evidence Updates with Likelihoods

Use `likelihood` for numeric evidence updates on `supports` and `contradicts` edges. Prefer explicit conditional likelihoods over a bare ratio:

```jsonl
{"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}, "reasoning": "The observed signal is more likely when the target claim is true."}
{"id": "E2-A1", "from": "E2", "to": "A1", "type": "contradicts", "likelihood": {"if_target_true": 0.1, "if_target_false": 0.7}, "reasoning": "The observed signal is less likely when the target claim is true."}
```

The computed update is:

```txt
likelihood_ratio = P(evidence | target true) / P(evidence | target false)
```

- `supports` requires computed `likelihood_ratio > 1`.
- `contradicts` requires computed `0 < likelihood_ratio < 1`.
- `likelihood_ratio` is allowed as shorthand when already calibrated, but do not set both `likelihood` and `likelihood_ratio` on the same edge.
- Omit `likelihood`/`likelihood_ratio` when an edge is explanatory but not calibrated enough to affect ranking; without one, `supports`/`contradicts` has no numeric cost effect.
- Multiple update edges multiply in odds space.
- The likelihood update should already include source reliability. Observation `prior` supplies its local starting probability and contributes through `leads_to`; neither that prior nor the observation's computed belief automatically dampens a `supports`/`contradicts` update.
- Correlated/overlapping evidence should be merged, represented with a `factor`, or represented with already-adjusted effective likelihoods; do not add a separate weight field.
- If an exact joint probability is known for required `leads_to` premises, use a `leads_to` factor with `aggregation.kind: "joint_probability"`; if correlated support/contradiction has a calibrated joint likelihood, use a `supports`/`contradicts` factor with conditional likelihood fields; if the whole target belief is calibrated, use explicit target `posterior` instead of stacking approximate updates.

`leads_to` is not a likelihood update. It forms the target's base belief by propagating ungrouped premise truth costs plus any `leads_to` factor joint-probability costs. `supports`/`contradicts` then update that base belief, with factor likelihoods replacing grouped member likelihood updates. If a target has explicit `posterior`, treat it as calibrated and do not also count incoming premise, factor, or likelihood edges for that target.

If an observation changes `truth_cost`/`search_cost` for any stored frontier item, `costs` recomputes priorities and `sort`/`next` reorders active frontier by best-first priority. If the target node is already visited/exhausted, do not reopen it just because the score changed. Add a new frontier item only when the observation creates new work. If no follow-up work exists, record event-level `no_new_work_reason`; if the node/family itself is complete, mark it `exhausted: true` with `exhaustion_reason`. Audit warns when an observation updates a visited node without either a new frontier item, `no_new_work_reason`, or node-level exhaustion proof.
