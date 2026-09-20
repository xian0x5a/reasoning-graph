# Reasoning Graph Cost Model

Truth/search cost, likelihood updates, confidence, bounded probes, and correlated evidence.

## Priors, Confidence, and Costs

Scores are type-bound:

| node | score |
| --- | --- |
| `assumption`, `candidate_solution` | `prior`, or `posterior` once calibrated |
| `evidence` | `confidence` |
| `derived` | no local score: `leads_to` premises carry its belief, or `posterior` once calibrated |
| `goal`, `constraint`, `test` | none — objectives, boundaries, and actions, not claims |

All scores are in `(0, 1]`. Zero is excluded because cost is `-ln(P)`; record impossibility in the claim or status instead of inventing a small number. Use coarse values and avoid fake precision.

- `prior` is belief before branch exploration. Do not overwrite it with `posterior`, which records the calibrated belief after evidence.
- `confidence` is reliability of the observation, not belief about the claim: official metadata changes, OCR misreads, transcripts go stale, and local scripts have bugs, so state how much you trust the reading.
- Mutually exclusive sibling assumptions should form a local distribution that sums to `1.0`; independent assumptions need not sum to `1.0`.
- Graph labels display the score with its field name. Helper reports derive candidate `belief` from `effective_truth_cost`; an explicit `posterior` overrides graph-derived updates and must not be derived from path/search costs.

A `derived` node carries no local score: its belief is the product of its `leads_to` premises, so premises `0.8` and `0.9` give belief `0.72`. At least one `leads_to` premise is required — `posterior` overrides premise propagation but does not replace the derivation, so a calibrated conclusion still shows what it was derived from. Doubt about the inference itself — clock skew, a rule that may not apply here — is an unstated premise, so model it as an `assumption` with a `prior` and link it with `leads_to`; the doubt then stays visible and updates with everything downstream.

Evidence can be wrong, so it carries `confidence`. A `test` is a procedure, not a claim: it carries no score, and its outcome is recorded as separate `evidence` (or `derived`) with its own score. A `goal` or `constraint` is the objective or boundary itself, so it also carries no score.

### Certainty is not an unknown score

`1.0` means certain, never "no score specified". For an unresolved hypothesis, state a justified estimate; `prior: 0.5` is a deliberately neutral start, and a node that carries no belief at all carries no score instead of a placeholder.

With no uncertain premises, finite likelihood ratios cannot move belief away from `1.0`: a neutral `prior: 0.5` with a supporting ratio of `2` gives belief `2/3`, and a contradicting ratio of `0.1` gives `1/11`, while a starting `1.0` stays at `1.0` either way.

### Required edge reasoning

Every edge requires `reasoning`: one to five sentences explaining the directed relationship, including `requires`, `prompts`, `answers`, and factor member edges. Repeating the edge type is not an explanation, and a factor's `reason` does not replace member-edge reasoning.

```json
{"from": "E1", "to": "D1", "type": "leads_to", "reasoning": "The deployment timestamp is earlier than the first failing request, so deployment preceded the outage."}
```

`validate`, `seed`, and `expand` enforce the limit with the packaged JSON Schema format `reasoning-sentences`: boundaries are `.`, `!`, or `?` followed by whitespace, optionally after closing quotes or brackets; final punctuation is optional, and decimals such as `0.75` do not split. External JSON Schema validators must enable `REASONING_FORMAT_CHECKER` to enforce the count. This is a deterministic length check, not a grammar or quality judge.

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

`truth_cost` measures current plausibility from the graph's probability model. `base_search_cost` measures local remaining effort/risk. Optional top-level `estimated_remaining_cost` is a heuristic estimate of remaining work: unmet criteria, missing evidence, unresolved constraints, confidence gap, dependency depth, or similar effort. It is not truth cost and should stay outside `cost_components`. `search_policy.estimated_remaining_weight` defaults to `1.0`; set it lower when rough heuristics should guide order without dominating local cost.

`search_cost` is frontier priority. Past work is sunk and does not accumulate into frontier priority. Priority queue order is by lowest `search_cost`, not highest belief alone. Ties break by frontier item id.

Two accumulation axes are easy to conflate. Belief accumulates through the claim graph: `leads_to` premises multiply into a derived node's belief, so premises `0.8` and `0.9` give `0.72` and cost `0.2231 + 0.1054`. Search depth does not accumulate: an item's priority reflects its own belief and remaining work, never the route taken to reach it, so items on the same node price identically at any depth.

Exact math is optional. Rough costs are acceptable when they preserve ordering and make the search better.

### Bounded Effort / Probe Priority

Brute-force, broad probing, sweeps, enumeration, or high-volume checking are not inherently low-cost just because a script is easy to run. Their search cost must include the committed effort budget.

A probe/brute-force branch may have low `search_cost` only when it is:

- tightly bounded (`max_attempts`, `max_seconds`, `max_items`, or equivalent),
- a cheap discriminator for a specific clue-derived hypothesis,
- stopped as soon as its budget or discriminator condition is reached,
- and recorded with `cost_components.effort_budget` plus `budget` metadata.

Example:

```json
{
  "id": "Q7",
  "node": "A7",
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
{"from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}, "reasoning": "The observed signal is more likely when the target claim is true."}
{"from": "E2", "to": "A1", "type": "contradicts", "likelihood": {"if_target_true": 0.1, "if_target_false": 0.7}, "reasoning": "The observed signal is less likely when the target claim is true."}
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
- The likelihood update should already include source reliability. Evidence `confidence` is displayed/audited and contributes when that evidence is a `leads_to` premise; it does not automatically dampen a `supports`/`contradicts` update.
- Correlated/overlapping evidence should be merged, represented with a `factor`, or represented with already-adjusted effective likelihoods; do not add a separate weight field.
- If an exact joint probability is known for required `leads_to` premises, use a `leads_to` factor with `aggregation.kind: "joint_probability"`; if correlated support/contradiction has a calibrated joint likelihood, use a `supports`/`contradicts` factor with conditional likelihood fields; if the whole target belief is calibrated, use explicit target `posterior` instead of stacking approximate updates.

`leads_to` is not a likelihood update. It forms the target's base belief by propagating ungrouped premise truth costs plus any `leads_to` factor joint-probability costs. `supports`/`contradicts` then update that base belief, with factor likelihoods replacing grouped member likelihood updates. If a target has explicit `posterior`, treat it as calibrated and do not also count incoming premise, factor, or likelihood edges for that target.

If evidence changes `truth_cost`/`search_cost` for any stored frontier item, `costs` recomputes priorities and `sort`/`next` reorders active frontier by best-first priority. If the target node is already visited/exhausted, do not reopen it just because the score changed. Add a new frontier item only when the evidence creates new work. If no follow-up work exists, record event-level `no_new_work_reason`; if the node/family itself is complete, mark it `exhausted: true` with `exhaustion_reason`. Audit warns when evidence updates a visited node without either a new frontier item, `no_new_work_reason`, or node-level exhaustion proof.
