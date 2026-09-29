# Reasoning Graph Cost Model

Scores, defaults, and the belief the rendered view computes from them. Read the first section to score; the rest explains what a reader sees.

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

Belief is computed only when the graph is rendered, for the reader. The state stores none, a state or patch carrying `belief` is rejected, and no command prints it: an agent that sees a belief tunes scores until the number moves.

Mutually exclusive sibling hypotheses do not have to sum to anything; the scale is too coarse for that. A `test` is a procedure, not a claim: record its outcome as a separate `observation` node.

### Notes on edges

An edge takes an optional `note`, the same field nodes have. Nothing forces one: most links are plain from the two node texts. Write a note when the score departs from the default, so a reader can check the weight, or when the link is not obvious.

```json
{"from": "O1", "to": "H1", "type": "supports", "score": 5, "note": "Only the token server writes this log line."}
```

The removed `reasoning` field is rejected.

### Belief computation

Belief is computed in cost space, where a probability `P` has cost `-ln(P)`:

```txt
local_probability = table[score], or table[default] for a claim without claim premises, or 1 for a premise-backed claim without a score
base_truth_cost(target) = -ln(local_probability) + sum(effective_truth_cost(ungrouped premises via leads_to)) + sum(-ln(leads_to group probability))
base_odds = P_base / (1 - P_base)
updated_odds = base_odds * product(ungrouped supports/contradicts ratios) * product(supports/contradicts group ratios)
effective_truth_cost = -ln(updated_odds / (1 + updated_odds))
belief = exp(-effective_truth_cost)
```

Belief accumulates through the claim graph: `leads_to` premises multiply into the target node's belief, so premises `0.7` and `0.9` give `0.63`.

Graph labels and candidate tables show effective belief; node details show the authored score beside it. See [belief display](rendering.md#belief-display).

### Evidence edges

- Every `supports` and `contradicts` edge updates its target, at its score or at the default 3.
- Multiple evidence edges multiply in odds space: a default hypothesis with two default supports has odds `1 * 2 * 2` and belief `0.8`.
- The edge score already includes how reliable the source is. An observation's own score contributes through `leads_to`; it does not dampen the observation's `supports`/`contradicts` edges.
- Evidence from a claim (`hypothesis` or `candidate_solution`) is only as strong as the claim: with source belief `b`, ratio `r` acts as `1 + b·(r − 1)`, treating a false source as uninformative. A group with claim sources uses the product of their beliefs. `supports` from a claim that is not evidence-grounded (`SKILL.md` stop gates) has no effect; `contradicts` always applies, scaled. Claim-sourced evidence is a truth dependency, so cycles through it are invalid.
- Correlated or overlapping evidence should be merged into one node or grouped (`schema/factors.md`), so it counts once. A group's score replaces its members' updates: two grouped supports at group score 3 double the odds once, not twice.
- `leads_to` premises that stand or fall together are grouped the same way; the group's score is read from the claim table as their joint probability and replaces their product.

`leads_to` is not an evidence update. It forms the target's base belief from the ungrouped premises and any `leads_to` groups. `supports`/`contradicts` then update that base belief.
