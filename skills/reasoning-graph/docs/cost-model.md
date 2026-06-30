# Reasoning Graph Cost Model

Truth/search cost, likelihood updates, confidence, bounded probes, and correlated evidence.

Use the installed `reasoning-graph` CLI for helper commands. If `reasoning-graph --help` is unavailable, install it with `uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"`.

## Priors, Confidence, and Costs

Use probabilities only where they mean something.

- `prior`: belief before branch exploration, for hypotheses/assumptions/candidate claims.
- `confidence`: source/result reliability for evidence, derived claims, and noisy test observations.
- `posterior`: explicit updated belief after tests/evidence, if useful. Do not overwrite `prior`; it is the audit trail for the starting belief.
- Mutually exclusive sibling assumptions should form a local distribution that sums to `1.0`.
- Independent assumptions use independent priors and do not need to sum to `1.0`.
- Use coarse numeric values; avoid fake precision.
- Show priors/confidence/costs to the user only when they affect the conclusion, ambiguity, or branch ranking.

Helper-generated reports derive table `belief` from `effective_truth_cost`. `posterior` is an explicit calibrated override stored on the node; do not derive or overwrite it from path/search costs. If `posterior` is present, graph-derived likelihood updates are treated as already accounted for.

Evidence can be wrong. Official metadata may change, OCR can misread, transcripts can be stale, and local scripts can have bugs. Add `confidence` when source reliability matters. Do not force fake priors onto goals, constraints, or deterministic procedures.

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

`search_cost` is frontier priority. Past work is sunk and does not accumulate into frontier priority. Priority queue order is by lowest `search_cost`, not highest belief alone.

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
{"from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}}
{"from": "E2", "to": "A1", "type": "contradicts", "likelihood": {"if_target_true": 0.1, "if_target_false": 0.7}}
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
