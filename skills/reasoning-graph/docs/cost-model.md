# Reasoning Graph Cost Model

Scores, defaults, and the belief the rendered view computes from them. Read the first section to score; the rest explains what a reader sees.

## Scores and defaults

One optional `score` from 1 to 5 is the only number you write, on claims and on evidence edges. Write it only where the default is wrong.

| score | claim | probability | evidence edge (likelihood ratio) |
| --- | --- | --- | --- |
| 1 | very unlikely | 0.1 | ×1.2 |
| 2 | unlikely | 0.3 | ×1.5 |
| 3 | open | 0.5 | ×2 |
| 4 | likely | 0.7 | ×3 |
| 5 | well established | 0.9 | ×5, the ceiling: stronger evidence still counts ×5; never proof |

The likelihood ratio is defined under Scores in `../SKILL.md`. A `contradicts` edge uses its reciprocal. An edge drawn from an observation that every rival explains lifts every claim it touches: a default `supports` edge to each of two rivals shows both at 67%, where no edge leaves both at 50%.

| object | default score |
| --- | --- |
| `observation` | 5 |
| `hypothesis`, `candidate_solution` | 3 |
| `supports`, `contradicts` edge | 3 |

- A claim with no score takes its default, unless it is deduced: it has premises (`premise_of` edges) or a premise group (choosing the edge, `../SKILL.md`). A deduced claim takes their joint belief and adds nothing of its own: a hypothesis at score 4 that is a candidate's only premise gives the candidate belief `0.7`, not `0.35`. `record` rejects a score on a deduced claim.
- Goals, constraints, and tests carry no score. Neither do `premise_of`, `yields`, `requires`, `prompts`, and `answers` edges; a test has no belief, so `yields` moves none.
- The scale has no certainty and no impossibility: even a score 5 `contradicts` edge is a ratio that other evidence can outweigh. An observation that settles a claim as false takes a `rules_out` edge instead (below).
- The removed fields `prior`, `confidence`, `probability`, and `posterior` on nodes and `likelihood` and `likelihood_ratio` on edges are rejected, not converted.

Belief is computed only when the graph is rendered, for the reader. The state stores none, a state or patch carrying `belief` is rejected, and the workflow commands (`record`, `refresh`, `audit`) print none: an agent that sees a belief tunes scores until the number moves. `html` and `mermaid` render it for readers, including the pre-claim reviewer (`review.md`), who never edits the graph.

Beliefs of rival claims are not normalised: the scale is too coarse for it, and a rival list is rarely complete, so normalising would let the last one standing win by elimination. List rivals that cannot both hold in an exclusive set (`../SKILL.md`). Each member keeps its own belief; the page flags a set with two members above 50%, which exclusive claims cannot both be, whether or not the set is complete. A `test` is a procedure, not a claim: record its outcome as a separate `observation` node.

### Notes on edges

An edge takes an optional `note`, the same field nodes have. Nothing forces one: most links are plain from the two node texts. Write a note when the score departs from the default, so a reader can check the weight, or when the link is not obvious.

```json
{"from": "O1", "to": "H1", "type": "supports", "score": 5, "note": "Only the token server writes this log line."}
```

The removed `reasoning` field is rejected.

### Belief computation

Belief is computed in cost space, where a probability `P` has cost `-ln(P)`:

```txt
local_probability = table[score or default] for a claim without premises, or 1 for a deduced claim, which takes no score
base_truth_cost(target) = -ln(local_probability) + sum(effective_truth_cost(ungrouped premises via premise_of)) + sum(-ln(premise group probability))
base_odds = P_base / (1 - P_base)
updated_odds = base_odds * product(ungrouped supports/contradicts ratios) * product(supports/contradicts group ratios)
effective_truth_cost = -ln(updated_odds / (1 + updated_odds))
belief = exp(-effective_truth_cost)
```

Belief accumulates through the claim graph: premises multiply into the target node's belief, so premises `0.7` and `0.9` give `0.63`.

Graph labels show effective belief; node details show the authored score beside it. See [belief display](rendering.md#belief-display).

### Evidence edges

- Every `supports` and `contradicts` edge updates its target, at its score or at the default 3.
- Multiple evidence edges multiply in odds space: a default hypothesis with two default supports has odds `1 * 2 * 2` and belief `0.8`.
- The edge score already includes how reliable the source is. An observation's own score contributes through `premise_of`; it does not dampen the observation's `supports`/`contradicts` edges.
- Evidence from a claim (`hypothesis` or `candidate_solution`) is only as strong as the claim: with source belief `b`, ratio `r` acts as `1 + b·(r − 1)`, treating a false source as uninformative. A group with claim sources uses the product of their beliefs. `supports` from a claim that is not evidence-grounded (`SKILL.md`, answer checks) has no effect; `contradicts` always applies, scaled. Claim-sourced evidence is a truth dependency, so cycles through it are invalid.
- Correlated or overlapping evidence should be merged into one node or grouped (`schema/factors.md`), so it counts once. A group's score replaces its members' updates: two grouped supports at group score 3 double the odds once, not twice.
- Premises that share a cause or overlap, so they hold or fail together, are grouped the same way; the group's score is read from the claim table as their joint probability and replaces their product.

`premise_of` and `supports` move belief in opposite ways as inputs pile up. Premises multiply: the first premise replaces the claim's default with the premise's belief; each further premise can only lower it. Evidence multiplies odds, so each added support raises it. Which one a link takes is the question under choosing the edge in `../SKILL.md`. The wrong one cuts a combined claim loose from its parts, above weak ones and below strong ones, or lowers a claim with every observation that confirms it.

### Ruled-out claims

A `rules_out` edge from an observation caps its target's belief at `0.001`, rendered `<1%`, after premises and evidence are applied. It is a status, not a weight: the cap also covers every claim resting on the target as a premise, grouped or not, and applies after their own evidence, so neither stacked support nor a premise group lifts a ruled-out claim back. Its `supports` toward other claims count for almost nothing, since claim-sourced evidence is scaled by the source's belief. A ruled-out claim is never evidence-grounded, so `audit` fails an answer that names it; that reads the edge, not a belief. Only an observation can rule a claim out, so one wrong inference cannot veto another claim, and changing the edge to `contradicts` undoes a wrong rule-out.

`premise_of` is not an evidence update. It forms the target's base belief from the ungrouped premises and any premise groups. `supports`/`contradicts` then update that base belief.
