---
name: reasoning-graph
description: >
  Use when solving complex reasoning problems by building a graph from goals,
  observations, constraints, hypotheses, and tests. Supports
  best-first frontier exploration, candidate solution paths, uncertainty/cost
  tracking, and optional Mermaid/HTML graph output.
---

# Reasoning Graph

Use this skill when a messy task is worth explicit graph/search state instead of one hidden linear chain: puzzles, root-cause analysis, ambiguous debugging, planning under uncertainty, or any case where hypotheses, observations, and candidate answers can diverge. If the task does not justify driver-loop overhead, do not use this skill.

Requirements: a subagent backend (the orchestrator delegates probes) and the helper CLI, installed separately; if `reasoning-graph --help` is unavailable, see `docs/install.md`. Without a subagent backend, do not use this skill.

## Driver loop

Every use keeps explicit state and follows this loop. Mutating commands rewrite the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout.

The queue leads the work. Put a direction on the graph before acting on it, and merge each result before choosing the next step, so every choice is made from the frontier. Solving first and filling in the graph afterward leaves the frontier nothing to rank: alternatives that were never on it when the choice was made did not compete.

1. **Frame goal.** Identify accepted goal(s). Add epistemic/blocker goals only when accepted by user or task wording.
2. **Seed graph.** Separate given/source-backed `observation`s, hard `constraint`s, and open `hypothesis` nodes. Seed initial nodes, edges, tests, and root frontier items.
3. **Pop focus before major work.** Run `next --pop` before major search, test, file inspection, verification, or branch selection; it recomputes costs and selects the lowest-cost active item.
4. **Choose treatment.** Resolve the popped item with `expand`, `assign`, or `rank`. `assign` hands research, test, or verify work to a subagent so the main thread stays on the queue (see Orchestrator and subagents).
5. **Merge reviewed results.** Add only supported findings/expansions. Calibrate `supports`/`contradicts` likelihoods or explicit `posterior`. Use `sort` only to persist recomputed frontier order before inspection/rendering; `next` already ranks before popping.
6. **Stop by policy** (gates below).
7. **Review final.** `validate`, `audit`, `stop-review`, then write final prose that matches the graph and invents no observations.

```bash
reasoning-graph init --goal "<goal>" --strict -o state.json
reasoning-graph seed state.json --patch seed.json
reasoning-graph next state.json --pop
# inspect popped item id, path, active_assumptions, related nodes

# Resolve popped item by one treatment:
reasoning-graph expand state.json --item <popped-item-id> --patch expansion.json
# or: reasoning-graph assign state.json --item <popped-item-id> --agent <agent>
# or: reasoning-graph rank state.json --item <popped-item-id>

# repeat pop -> resolve until a stop gate is satisfied

reasoning-graph stop state.json --reason "<policy-grounded reason>" --outcome <outcome> -o state.stopped.json
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json
reasoning-graph stop-review state.stopped.json --draft answer.md
```

Patch shape for `seed` and `expand`:

```json
{
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Observed fact", "source": "user prompt", "prior": 0.9},
    {"id": "H1", "type": "hypothesis", "text": "Plausible branch", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Check branch"}
  ],
  "edges": [
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "likelihood_ratio": 2, "reasoning": "The observed signal is more likely when the target claim is true."},
    {"id": "H1-T1", "from": "H1", "to": "T1", "type": "prompts", "reasoning": "This claim motivates the follow-up check."}
  ],
  "frontier": [
    {"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.2}, "estimated_remaining_cost": 0.5}
  ]
}
```

`expand` may also use `update_nodes`, `factors`, and `no_new_work_reason`.

## Event rules the driver enforces

- Do not call `next --pop` again until the pending popped item is recorded through `expand`, `assign`, or `rank`. `stop` requires no pending item; a candidate-bearing `stop` auto-ranks only after terminal preflight passes.
- Use `seed` for the initial root frontier or later unrelated user clues; use `expand` for work caused by the current popped/assigned item.
- Assigned items are in-flight, not active frontier; merge returned work with `expand --item <assigned-item>`.
- Under strict policy, expanding a `test` item must record its result: an `observation` node linked by `leads_to` from the test, which then `supports`/`contradicts` the claim it tested; a conclusion drawn from the observation is a separate `hypothesis` linked by `leads_to` from the observation. A failed or inconclusive probe is still a result; record it before the next pop so siblings re-rank on real cost. Shapes: `docs/schema/tests.md`.
- Under strict policy, an expansion that adds no frontier item and no candidate must record `no_new_work_reason`.
- For parallel work, decompose one focus item into explicit independent sub-probes before fanout.

## Orchestrator and subagents

The main agent is an orchestrator. It maintains the queue and makes decisions: goal framing, canonical state, frontier priority, treatment choice, merge decisions, stop policy, and the final answer. Subagents can do the work that produces observations: source research, code/file inspection, docs lookup, hypothesis probes, running tests, verification of high-impact claims, candidate audits, and adversarial review. Delegating keeps raw observations out of the orchestrator's context and lets independent probes run in parallel; the orchestrator decides what to inspect itself and how wide each probe is.

A delegation unit is one bounded probe: one frontier item, hypothesis, test, source family, or candidate audit, with a stop rule, an output contract, and no decision authority.

Child output contract: target, observations for/against with source refs, proposed nodes/edges, confidence or likelihood impact, residual uncertainty, suggested next probes, and blocked/stop reason when applicable. If a child tried interpretations beyond its item, it lists each one with its result, failures included; the controller records them as sibling `hypothesis` nodes with their `supports`/`contradicts` observations instead of keeping only the winner. The controller reviews and applies accepted changes via `expand --item <assigned-item> --patch <patch>`.

`assign --agent` names a subagent actually started for that item. Work the controller does itself is recorded by expanding the popped item directly; an `assign` with no matching child makes the trace claim delegation that did not happen.

## Schema quick reference

Enough to build and review state during normal work; validate real files with `reasoning-graph validate`. Machine-readable contracts: `reasoning-graph schema state` and `reasoning-graph schema patch`.

Scores: `prior` is local input, `belief` is computed output, `posterior` is an explicit calibrated override that bypasses the node's inputs until refreshed or removed. Claims need a prior, a posterior, belief-bearing `leads_to` premises, or a calibrated joint factor. Premise-backed candidates may omit priors; add one only for uncertainty not already counted in the premises. Goals, constraints, and tests carry no score. Read `docs/cost-model.md` before assigning scores or likelihoods.

Node types:

- `goal` — target to prove, solve, decide, or explain
- `observation` — what was seen, given, verified, or source-backed, recorded as observed rather than interpreted; `prior` records its local starting probability, accounting for observation/transcription/source reliability
- `constraint` — boundary valid answers must satisfy; connect with `requires`
- `hypothesis` — claim not yet established. Competing interpretations are sibling hypotheses: atomic, one frontier item each, re-ranked against each other; an intermediate step toward the goal is a hypothesis with its own sub-search and may be compound; a blocker is a hypothesis backed by observations. One node per claim for its whole life: `prior` while open, `leads_to` premises once proved, never a second node for the proved form
- `test` — action/check/procedure; carries no score and carries no belief until its result `observation` is recorded
- `candidate_solution` — possible answer; requires `answer_kind` and a `candidate_solution -> goal` `answers` edge to an accepted goal

Edge types (every edge needs nonblank `reasoning`, one to five sentences, including factor member edges):

- `requires` — hard dependency; prefer `goal -> constraint` or `candidate_solution -> constraint`
- `supports` — positive belief update; numeric form uses `likelihood` or `likelihood_ratio > 1`
- `contradicts` — negative belief update; numeric form uses `likelihood` or `0 < likelihood_ratio < 1`; it lowers belief but does not disqualify the target by itself
- `prompts` — non-evidential provenance from clue/claim/branch to a test or follow-up; no belief update
- `leads_to` — premise/dependency used to derive a target's base belief
- `answers` — candidate satisfies a goal; must be `candidate_solution -> goal`

Factors (`docs/schema/factors.md`):

- A factor is a top-level anti-double-counting record: incoming numeric edges to one target that share a source, observation, latent cause, or logical overlap are aggregated together instead of multiplied as independent evidence. Ungrouped edges stay independent.
- `leads_to` factors use `aggregation: {"kind": "joint_probability", "probability": ...}`; `supports`/`contradicts` factors use `aggregation: {"kind": "likelihood", "if_target_true": ..., "if_target_false": ...}`, never a direct `likelihood_ratio`.
- In patches, `factors` adds or replaces by `id`; audit events are recorded automatically.

Goals and candidates (`docs/schema/goals.md`):

- `answer_kind` values: `exact_answer`, `exact_method`, `method_hypothesis`, `clue_path`, `blocker`. For concrete solve goals only `exact_answer` and `exact_method` may answer the accepted goal; the others need explicit method/clue/epistemic goals or stay as `hypothesis` nodes.
- "Not solved", "cannot establish", or "missing dependency" is a stop outcome or hypothesis blocker, not a candidate, unless the user accepted an epistemic/negative goal.
- Use multiple `goal` nodes only when the user accepts multiple outcomes (solve, prove impossible, insufficient information). Chained sub-goals are plain `goal` nodes linked `parent --requires--> child`; a goal is answered only when a candidate answers it and every required sub-goal is answered.
- Without `goal_policy.accepted_goals`, all goals are acceptable destinations. `preferred_goals` affects presentation/priority only; `optional_goals` may stay unanswered at a candidate-bearing stop.

Report and presentation (`docs/schema/reporting.md`):

- `summary.answer`, `report.answer`, and the final draft must name the best candidate of each accepted goal by id or exact text; an answer matching no candidate fails stop-review.
- Rank and viability derive from the graph; keep words like `Best`, `Second`, `viable`, or `rejected` out of node text and candidate names.

## Cost and priority

Use coarse numbers.

```txt
truth_cost = -ln(P(claim true))
base_search_cost = effective_truth_cost + local work costs
search_cost = base_search_cost + estimated_remaining_weight * estimated_remaining_cost
```

- `truth: "auto"` computes belief from local `prior`, inherited premises, and likelihood updates unless `posterior` overrides it; the engine never writes computed belief back into node scores.
- `search_cost` is frontier priority; lower pops first. Parent path cost is sunk and does not accumulate.
- `estimated_remaining_cost` sits on the frontier item top level, not inside `cost_components`. Its weight is state-level `search_policy.estimated_remaining_weight`, which `init --strict` sets to 1.0.
- Broad probes/brute force need explicit `effort_budget` and bounded `budget` metadata.
- Likelihood updates from observations already account for source reliability; observation `prior` does not scale them. Evidence from a hypothesis or candidate is scaled by its belief `b` (ratio `r` acts as `1 + b·(r − 1)`), support from an ungrounded claim has no effect, and evidence cycles between claims are invalid.

## Exploration rules

Input ledger:

- Extract the accepted `goal` first. If goals conflict, ask or state the chosen primary goal.
- Classify given/source-backed facts as `observation`s, answer boundaries as `constraint`s, and plausible interpretations as `hypothesis` nodes/frontier items. Keep facts with different logical roles as separate observation nodes with source refs and an explicit reliability score.
- Mark inferred constraints as inferred; ask the user when the inference is high-impact or ambiguous.
- Before the initial frontier, one bounded context pass may add cheap source-backed observations. After search starts, non-trivial checks are `test`/frontier work with results appended during `expand`.

Branching:

- How wide to branch is the agent's call. When a choice between interpretations matters, put the contenders on the graph as sibling `hypothesis` nodes with frontier items so the frontier can rank them; `audit` reports `peak_live_frontier` as a measure of how much the frontier was used.
- Price cheap interpretations of authoritative clues (official hints, docs, logs, test failures) below broad brute-force probes.
- A failed bounded test penalizes only the exact tested interpretation, not the whole family. To close a family deliberately, set `exhausted: true` with `exhaustion_reason`.
- Reopen a visited node only when a new observation creates new work; score-only updates stay closed.

Candidates:

- Candidates are usually conclusions of explored branches. Early placeholders are valid only when user-supplied, obvious from strong direct observations, or explicitly weak; a candidate entering the frontier before its support is expanded gets high truth/constraint-tension cost so it cannot outrank observation-backed branches.
- A viable candidate answers an accepted goal, satisfies known constraints, has no unresolved contradiction, and states remaining open hypotheses/uncertainty. Constraint violations add explicit cost/blocking observations to affected branches.
- Ranked report candidates correspond to explored, tested, or observation-penalized branches; unexplored alternatives are mentioned as possibilities, not ranked.

## Stop gates

Stop is metric-gated. A normal stop is allowed only when at least one holds:

- event-reachable frontier is exhausted
- enough viable candidates have been explored, usually `min_viable_candidates: 3` for comparison/search tasks
- strongest viable candidate crosses an explicit threshold, usually `belief_threshold: 0.8`
- explicit external budget is reached and remaining live frontier is recorded as unfinished, not exhausted

Rules:

- `solved` and `candidate_threshold_met` stops need an evidence-grounded best candidate, and the belief threshold counts only grounded candidates. A claim is grounded when all of its `leads_to` premises are grounded, or when its evidence favors it (net likelihood ratio > 1) counting `supports` only from grounded sources and `contradicts` from any source; observations are the base. Priors and posteriors never ground a claim, and a claim with only contradicting evidence is still being carried by its prior. `stop` names the ungrounded claims: test them, or stop with `budget_exhausted`/`inconclusive` and report them as open hypotheses.
- A hypothesis that wins by elimination needs that elimination recorded as positive evidence: an observation such as "H2 ruled out" that `supports` the survivor, or a `leads_to` premise from it. Contradicting its siblings does not raise the survivor's belief.
- `solved`, `candidate_threshold_met`, and `candidate_count_met` stops are rejected while any accepted goal is unanswered. Stop with `inconclusive`/`budget_exhausted` instead, or list the goal in `goal_policy.optional_goals`.
- An epistemic/blocker stop is allowed while meaningful answer-goal frontier is live only if `stop_policy` explicitly allows it. For benchmark/search tasks use strict `stop_policy`: `min_viable_candidates: 3`, `belief_threshold: 0.8`, `max_live_frontier_items: 0`, `require_frontier_exhausted_for_epistemic_stop: true`, `severity: "error"`.
- Close alternatives only when likelihood/cost updates make them clearly dominated. Contradicted candidates may stay visible with lower belief but satisfy high-confidence stop targets only if effective truth cost still passes.
- Ask the user before deepening search when remaining exploration would cost meaningful time.
- The stop reason names the gate that fired.
- Treat `audit`/`stop-review` warnings on benchmark or published artifacts as actionable: fix state/events or explain why the warning is acceptable. Mechanics: `docs/driver.md`.

## Output

Default final response: answer/recommendation, concise proof path, open hypotheses relied on, top competing candidates when ambiguity matters, contradictions only if important, next test/action if uncertainty remains. Present a user-facing proof path, not raw scratch state or hidden chain-of-thought.

Graph/HTML artifact only when requested or approved; ask first otherwise. Generate it from validated state (layout, offline mode, canvas rules: `docs/rendering.md`):

```bash
reasoning-graph html state.json -o <path>.html
```

## Reference docs

- `docs/schema/factors.md` — `factors` examples and validation rules
- `docs/schema/goals.md` — candidate, answer-kind, multiple-goal, lemma-lifecycle, and proof-vocabulary rules
- `docs/schema/tests.md` — test lifecycle and result observation pattern
- `docs/schema/reporting.md` — report and presentation metadata examples
- `docs/cost-model.md` — probability/cost math, likelihoods, bounded probes
- `docs/driver.md` — state JSON, helper commands, event/audit/stop-review mechanics
- `docs/rendering.md` — final prose, graph/HTML artifacts, canvas rules
- `docs/install.md` — one-time helper CLI install
