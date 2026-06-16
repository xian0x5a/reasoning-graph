---
name: reasoning-graph
description: >
  Use when solving complex reasoning problems by building a graph from goals,
  evidence, constraints, derivations, and hypothetical branches. Supports
  best-first frontier exploration, candidate solution paths, uncertainty/cost
  tracking, and optional Mermaid/HTML graph output.
---

# Reasoning Graph

Use this skill when a messy task needs explicit alternatives instead of one hidden linear chain: puzzles, root-cause analysis, ambiguous debugging, planning under uncertainty, or any case where assumptions, evidence, and candidate answers can diverge.

Default output is compact. Create graph/HTML artifacts only when requested or when they materially improve understanding; ask first if artifact generation was not requested.

## Core operating loop

1. **Frame goal.** Identify accepted goal(s). If the user only asked to solve, use one `goal`; add epistemic/blocker goals only when accepted by user or task wording.
2. **Extract ledger.** Separate given/source-backed `evidence`, hard `constraint`s, and uncertain `assumption`s. Do not treat plausible interpretations as evidence.
3. **Initialize frontier.** Add unresolved assumptions/tests/candidate-support work as frontier items with coarse priors/costs.
4. **Let driver choose.** For complex graph mode, run `./scripts/rg.py next state.json --pop -i` before major reasoning, tool use, searches, tests, or branch selection.
5. **Expand divergently.** For popped item, add meaningful sibling branches/tests/evidence/candidates. Do not tunnel on first plausible answer.
6. **Update beliefs.** Add result evidence and calibrated `supports`/`contradicts` likelihoods or explicit posterior. Re-sort frontier.
7. **Stop by policy.** Stop only when frontier is exhausted, enough viable candidates exist, a candidate crosses threshold, budget is hit, or a real blocker is proved.
8. **Review final.** Validate/audit state, then ensure final prose matches graph and invents no evidence.

## Canonical model quick reference

Node types:

- `goal` — target to prove, solve, decide, or explain
- `evidence` — observed/given/verified/source-backed statement
- `constraint` — boundary valid answers must satisfy
- `derived` — conclusion from prior nodes
- `assumption` — uncertain branch point with numeric `prior`
- `test` — action/check; use `status: proposed|performed|inconclusive`
- `candidate_solution` — possible answer; must have `answer_kind` and `candidate_solution -> goal` `answers` edge

Edge types:

- `requires` — hard dependency, usually `goal -> constraint` or candidate/branch -> constraint
- `supports` — positive evidence update; numeric form uses `likelihood` or `likelihood_ratio > 1`
- `contradicts` — negative evidence update; numeric form uses `0 < likelihood_ratio < 1`; does not delete target
- `prompts` — non-evidential provenance from clue/claim to test/follow-up
- `leads_to` — premise/dependency for deriving target base belief
- `assumes` — branch proceeds under assumption
- `answers` — `candidate_solution -> goal`

Use top-level `factors` for correlated/non-independent incoming numeric inputs. Prefer `factors` over legacy `premise_groups`.

Details: `docs/schema.md`.

## Cost and priority quick reference

Use coarse numbers. Avoid fake precision.

```txt
truth_cost = -ln(P(claim true))
base_search_cost = effective_truth_cost + local work costs
search_cost = base_search_cost + estimated_remaining_weight * estimated_remaining_cost
```

- `truth: "auto"` computes node truth from prior/confidence/posterior plus graph evidence.
- `search_cost` is frontier priority; lower pops first.
- Parent path does **not** accumulate cost; past work is sunk.
- `estimated_remaining_cost` belongs on frontier item top level, not inside `cost_components`.
- Broad probes/brute force need explicit `effort_budget` and bounded `budget` metadata.
- `confidence` displays/source-ranks evidence, but likelihood edge reliability must be baked into the likelihood update.
- Explicit `posterior` means calibrated override; do not also count incoming evidence for that target.

Details: `docs/cost-model.md`.

## Helper commands

Run from skill directory or call script by path.

```bash
./scripts/rg.py template strict -o state.json
./scripts/rg.py init --goal "Diagnose outage" --strict -o state.json
./scripts/rg.py doctor state.json
./scripts/rg.py validate state.json
./scripts/rg.py costs state.json -i
./scripts/rg.py sort state.json -i
./scripts/rg.py frontier state.json
./scripts/rg.py next state.json --pop -i
./scripts/rg.py expand state.json --item Q7 --patch expansion.json -i
./scripts/rg.py select state.json --node CS1 -i
./scripts/rg.py stop state.json --reason "best candidate verified" --outcome solved -o state.stopped.json
./scripts/rg.py audit state.json
./scripts/rg.py mermaid state.json > graph.mmd
./scripts/rg.py html state.json -o graph.html
```

Do not call `next --pop` again until the pending popped item is expanded, selected, or intentionally stopped.

Details: `docs/driver.md`.

## Expansion rules that matter most

- Assumptions should be atomic/testable, not answer-shaped bundles.
- Candidate solutions are usually conclusions of explored branches, not initial buckets.
- For concrete solve goals, only `exact_answer` and `exact_method` should answer accepted goal.
- Do not make “not solved” / “insufficient evidence” a candidate unless goal is explicitly epistemic.
- Authoritative clues deserve interpretation branches before broad brute-force branches.
- Failed bounded tests penalize exact tested interpretation, not whole clue family.
- High-salience clue/family expansions should usually add at least 3 child branches: direct/literal, structural/transform, low-prior wildcard. If fewer are meaningful, record `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof.

Details: `docs/exploration.md`.

## Stop and audit rules

Default stopping must be metric-gated, not discretionary. Normal stop is allowed when at least one is true:

- event-reachable frontier exhausted
- enough viable candidates explored, usually `min_viable_candidates: 3` for comparisons
- strongest viable candidate crosses explicit threshold, e.g. `belief_threshold: 0.8`
- external budget reached and remaining live frontier is recorded as unfinished

For benchmark/search tasks, prefer:

```json
"stop_policy": {
  "min_viable_candidates": 3,
  "belief_threshold": 0.8,
  "max_live_frontier_items": 0,
  "require_frontier_exhausted_for_epistemic_stop": true,
  "severity": "error"
}
```

Before final in driver mode:

```bash
./scripts/rg.py validate state.json
./scripts/rg.py audit state.json
```

Treat audit warnings as actionable for benchmark/published artifacts: fix state/events or explicitly explain remaining warnings.

## Output modes

Compact mode default:

1. answer/recommendation
2. concise proof path
3. key assumptions
4. top competing candidates when ambiguity matters
5. contradictions only if important
6. next test/action if uncertainty remains

Graph mode when requested:

1. persist state JSON, usually in `/tmp`
2. validate/audit
3. generate baseline artifact with `./scripts/rg.py html state.json -o <path>.html`
4. include summary, candidate table, readable evidence/constraint details, curated presentation graph, and full audit graph

Do not expose hidden chain-of-thought or raw scratch state. Provide user-facing proof path / reasoning summary.

Details: `docs/rendering.md`.

## Final checklist

- Goal explicit?
- Evidence separated from constraints?
- Assumptions scoped and assigned priors?
- Every viable candidate actually answers accepted goal?
- Alternatives kept alive or explicitly contradicted/exhausted?
- High-salience clue families expanded, live, or exhausted with reason?
- Priors/costs shown only when useful?
- Uncertainty labeled?
- Driver loop used before major search moves on complex tasks?
- Stopped state semantically reviewed before final?
- Graph HTML, if requested, generated from validated state with helper?

## Reference docs

- `docs/schema.md` — full schema, factors, goal policy, report metadata
- `docs/cost-model.md` — probability/cost math, likelihoods, bounded probes
- `docs/exploration.md` — ledger extraction, branching, stopping, candidate hygiene
- `docs/driver.md` — state JSON, helper commands, event/audit semantics
- `docs/rendering.md` — compact output, graph mode, HTML/canvas rules
- `schemas/state.schema.json` and `schemas/patch.schema.json` — machine-readable state/patch contracts
