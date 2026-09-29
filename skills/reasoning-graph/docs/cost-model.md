# Reasoning Graph Cost Model

Scores, defaults, computed belief, and correlated evidence.

## Scores and defaults

One optional `score` from 1 to 5 is the only number you write, on claims and on evidence edges. Write it only where the default is wrong.

| score | claim | probability | evidence edge | ratio |
| --- | --- | --- | --- | --- |
| 1 | very unlikely | 0.1 | barely bears on the target | 1.2 |
| 2 | unlikely | 0.3 | weak | 1.5 |
| 3 | open | 0.5 | moderate | 2 |
| 4 | likely | 0.7 | strong | 3 |
| 5 | well established | 0.9 | decisive | 5 |

A `contradicts` edge uses the reciprocal of its ratio.

| object | default score |
| --- | --- |
| `observation` | 5 |
| `hypothesis`, `candidate_solution` | 3 |
| `supports`, `contradicts` edge | 3 |

- A claim with no score and no claim among its `leads_to` premises takes its default.
- A claim with `leads_to` premises from other claims inherits their belief. Without a score it adds nothing of its own: a hypothesis at score 4 leading to an unscored candidate gives the candidate belief `0.7`, not `0.35`.
- A score on a premise-backed claim is a further local factor: premise `0.7` and score 5 give `0.63`. Write one only for uncertainty the premises do not already carry.
- Goals, constraints, and tests carry no score. Neither do `leads_to`, `requires`, `prompts`, and `answers` edges.
- The scale has no certainty and no impossibility. Record a ruled-out claim in its text or a `contradicts` edge.
- The removed fields `prior`, `confidence`, `probability`, and `posterior` on nodes and `likelihood` and `likelihood_ratio` on edges are rejected, not converted.

`belief` is output only: the CLI writes it on each claim, record patches reject it, and `validate` fails when a stored value no longer matches the graph. The engine never writes a computed value into `score`.

Mutually exclusive sibling hypotheses do not have to sum to anything; the scale is too coarse for that. A `test` is a procedure, not a claim: record its outcome as a separate `observation` node.

### Required edge reasoning

Every edge requires nonblank `reasoning` explaining the directed relationship, including `requires`, `prompts`, `answers`, and factor member edges. Aim for one to five sentences. Repeating the edge type is not an explanation, and a factor's `reason` does not replace member-edge reasoning.

```json
{"id": "E1-D1", "from": "E1", "to": "D1", "type": "leads_to", "reasoning": "The deployment timestamp is earlier than the first failing request, so deployment preceded the outage."}
```

State and patch schemas enforce nonblank text with standard string constraints; no custom format checker is needed. Sentence count is guidance, not a rejection rule: abbreviations and punctuation are not reliable sentence boundaries. Explain the relationship meaningfully; validation cannot judge prose quality.

### Belief computation

Belief is computed in cost space, where a probability `P` has cost `-ln(P)`:

```txt
local_probability = table[score], or table[default] for a claim without claim premises, or 1 for a premise-backed claim without a score
base_truth_cost(target) = -ln(local_probability) + sum(effective_truth_cost(ungrouped premises via leads_to)) + sum(-ln(leads_to factor joint_probability))
base_odds = P_base / (1 - P_base)
updated_odds = base_odds * product(ungrouped supports/contradicts ratios) * product(supports/contradicts factor ratios)
effective_truth_cost = -ln(updated_odds / (1 + updated_odds))
belief = exp(-effective_truth_cost)
```

Belief accumulates through the claim graph: `leads_to` premises multiply into the target node's belief, so premises `0.7` and `0.9` give `0.63`. `reasoning-graph beliefs state.json` prints the computed belief of every claim.

Graph labels and candidate tables show effective belief; node details show the authored score beside it. See [belief display](rendering.md#belief-display).

### Evidence edges

- Every `supports` and `contradicts` edge updates its target, at its score or at the default 3.
- Multiple evidence edges multiply in odds space: a default hypothesis with two default supports has odds `1 * 2 * 2` and belief `0.8`.
- The edge score already includes how reliable the source is. An observation's own score contributes through `leads_to`; it does not dampen the observation's `supports`/`contradicts` edges.
- Evidence from a claim (`hypothesis` or `candidate_solution`) is only as strong as the claim: with source belief `b`, ratio `r` acts as `1 + b·(r − 1)`, treating a false source as uninformative. A factor with claim inputs uses the product of their beliefs. `supports` from a claim that is not evidence-grounded (`SKILL.md` stop gates) has no effect; `contradicts` always applies, scaled. Claim-sourced evidence is a truth dependency, so cycles through it are invalid.
- Correlated or overlapping evidence should be merged or grouped with a `factor`, so it counts once.
- If an exact joint probability is known for required `leads_to` premises, use a `leads_to` factor with `aggregation.kind: "joint_probability"`; if correlated support/contradiction has a calibrated joint likelihood, use a `supports`/`contradicts` factor with conditional likelihood fields.

`leads_to` is not an evidence update. It forms the target's base belief by propagating ungrouped premise truth costs plus any `leads_to` factor joint-probability costs. `supports`/`contradicts` then update that base belief, with factor likelihoods replacing grouped member updates.
