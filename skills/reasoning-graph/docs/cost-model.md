# Reasoning Graph Cost Model

Local probability inputs, computed belief, and correlated evidence.

## Local input and computed belief

| concept | role |
| --- | --- |
| `prior` | Optional local starting-probability input, including observation or inference reliability |
| Computed `belief` | Output after premise propagation and likelihood updates, reported from effective truth cost and stored on each claim by the CLI |

Claim nodes (`observation`, `hypothesis`, and `candidate_solution`) accept `prior`. Each claim requires a **belief source**: a local prior, a source inherited through `leads_to` premises, or a calibrated joint-probability factor. A chain of unscored claims, a scoreless goal/constraint/test, or likelihood updates alone cannot supply a starting belief. `validate` and `record` check grounding on the complete graph; patch schemas permit omitted scores because their premises may already exist in the state.

Authored probabilities are in `(0, 1]`. Zero is excluded because cost is `-ln(P)`; record impossibility in the claim or status instead of inventing a small number. Use coarse values and avoid fake precision. Removed node fields `confidence`, `probability`, and `posterior` are rejected, not converted: no authored value overrides the computed belief. `belief` is output only: the CLI writes it on each claim, record patches reject it, and `validate` fails when a stored value no longer matches the graph.

A local `prior` multiplies premise belief. **Omit it when it merely repeats uncertainty already represented by the premises.** A hypothesis at `0.6` leading to an unscored candidate gives candidate belief `0.6`, not `0.3`; adding a candidate `prior: 0.5` represents additional uncertainty. On a premise-backed node, `prior` is a local factor, not an estimate of the already-aggregated conclusion.

For a soft inference, observation `prior: 0.8` times inference `prior: 0.9` gives base belief `0.72`. Alternatively, put inference validity in a separate hypothesis with `prior: 0.9` and a `leads_to` edge when it deserves independent scrutiny. Use one representation, not both. Omitting the local prior adds no extra uncertainty; validation checks grounding, not logical entailment. Keep derivation edges to explain conclusions, even when a local prior alone satisfies validation.

The engine computes effective belief from this base and likelihood updates; it never writes that result into a node's `prior`. For example, base `0.72` and supporting ratio `2` give computed belief `36/43`, while the authored priors remain `0.8` and `0.9`. Changing the premises or likelihoods changes the next computed result.

Graph labels and candidate tables show effective belief; node details distinguish that result from the local prior. See [belief display](rendering.md#belief-display).

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

### Belief computation

Belief is computed in cost space, where a probability `P` has cost `-ln(P)`:

```txt
truth_cost = -ln(P(claim true))
base_truth_cost(target) = local_truth_cost(target) + sum(effective_truth_cost(ungrouped premises via leads_to)) + sum(-ln(leads_to factor joint_probability))
base_odds = P_base / (1 - P_base)
updated_odds = base_odds * product(ungrouped supports/contradicts likelihood ratios) * product(supports/contradicts factor likelihood ratios)
effective_truth_cost = -ln(updated_odds / (1 + updated_odds))
belief = exp(-effective_truth_cost)
```

Belief accumulates through the claim graph: `leads_to` premises multiply into the target node's belief, so premises `0.8` and `0.9` give `0.72` and cost `0.2231 + 0.1054`. `reasoning-graph beliefs state.json` prints the computed belief of every claim.

Exact math is optional. Rough values are acceptable when they preserve which candidate is stronger.

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
- The likelihood update from an observation should already include source reliability. Observation `prior` supplies its local starting probability and contributes through `leads_to`; neither that prior nor the observation's computed belief dampens its `supports`/`contradicts` update.
- Evidence from a claim (`hypothesis` or `candidate_solution`) is only as strong as the claim: with source belief `b`, ratio `r` acts as `1 + b·(r − 1)`, treating a false source as uninformative. A factor with claim inputs uses the product of their beliefs. `supports` from a claim that is not evidence-grounded (`SKILL.md` stop gates) has no effect; `contradicts` always applies, scaled. Claim-sourced evidence is a truth dependency, so cycles through it are invalid.
- Correlated/overlapping evidence should be merged, represented with a `factor`, or represented with already-adjusted effective likelihoods; do not add a separate weight field.
- If an exact joint probability is known for required `leads_to` premises, use a `leads_to` factor with `aggregation.kind: "joint_probability"`; if correlated support/contradiction has a calibrated joint likelihood, use a `supports`/`contradicts` factor with conditional likelihood fields.

`leads_to` is not a likelihood update. It forms the target's base belief by propagating ungrouped premise truth costs plus any `leads_to` factor joint-probability costs. `supports`/`contradicts` then update that base belief, with factor likelihoods replacing grouped member likelihood updates.
