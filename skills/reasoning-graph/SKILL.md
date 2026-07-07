---
name: reasoning-graph
description: >
  Use when solving complex reasoning problems by building a graph from goals,
  evidence, constraints, derivations, and hypothetical branches. Supports
  best-first frontier exploration, candidate solution paths, uncertainty/cost
  tracking, and optional Mermaid/HTML graph output.
---

# Reasoning Graph

Use this skill when a messy task is worth explicit graph/search state instead of one hidden linear chain: puzzles, root-cause analysis, ambiguous debugging, planning under uncertainty, or any case where assumptions, evidence, and candidate answers can diverge. If the task does not justify driver-loop overhead, do not use this skill.

Default final output is compact prose. Create graph/HTML artifacts only when requested or when they materially improve understanding; ask first if artifact generation was not requested.

## Required driver loop

Every reasoning-graph skill use keeps explicit state and follows the driver loop. If the task does not justify this overhead, do not use this skill.

Mutating CLI commands rewrite the input state file by default. Use `-o <path>` for a separate output file or `-o -` for stdout.

1. **Frame goal.** Identify accepted goal(s). Add epistemic/blocker goals only when accepted by user or task wording.
2. **Seed graph.** Separate given/source-backed `evidence`, hard `constraint`s, and uncertain `assumption`s. Seed initial nodes, edges, tests, and root frontier items.
3. **Pop focus before major work.** Run `next --pop` before major search, test, file inspection, verification, or branch selection; `next` computes current costs and selects the lowest-cost active item.
4. **Choose treatment.** Resolve the popped item with `expand`, `assign`, `rank`, or `stop`. Use subagents for observation-heavy probe/verify work.
5. **Merge reviewed results.** Add only supported findings/expansions. Calibrate `supports`/`contradicts` likelihoods or explicit `posterior`. Use `sort` only when you want to persist recomputed frontier order before inspection/rendering; `next` already ranks before popping.
6. **Stop by policy.** Stop only when frontier is exhausted, enough viable candidates exist, a candidate crosses threshold, budget is hit, or a real blocker is proved.
7. **Review final.** Validate, audit, run semantic stop-review, then ensure final prose matches graph and invents no evidence.

Executable skeleton:

```bash
reasoning-graph init --goal "<goal>" --strict -o state.json
reasoning-graph seed state.json --patch seed.json
reasoning-graph next state.json --pop
# inspect popped item id, path, assumptions, related nodes

# Resolve popped item by one treatment:
reasoning-graph expand state.json --item <popped-item-id> --patch expansion.json
# or: reasoning-graph assign state.json --item <popped-item-id> --agent <agent>
# or: reasoning-graph rank state.json --item <popped-item-id>

# repeat pop -> resolve until stop policy is satisfied

reasoning-graph stop state.json --reason "<policy-grounded reason>" --outcome <outcome> -o state.stopped.json
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json
reasoning-graph stop-review state.stopped.json --draft answer.md
```

Minimal patch shapes:

```json
{
  "nodes": [
    {"id": "E1", "type": "evidence", "text": "Observed fact", "source": "user prompt", "confidence": 0.9},
    {"id": "A1", "type": "assumption", "text": "Plausible branch", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Check branch"}
  ],
  "edges": [
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 2},
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"}
  ],
  "frontier": [
    {"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.2}}
  ]
}
```

Use the same patch shape for `seed` and `expand`; `expand` may also use `update_nodes`, `factors`, `no_new_work_reason`, `under_branching_reason`, and `existing_sibling_frontier`. Details: `docs/driver.md` and `docs/schema/`.

Rules that prevent fake traces:

- Do not call `next --pop` again until the pending popped item is recorded through `expand`, `assign`, or `rank`; candidate-bearing `stop` may close a pending item.
- Use `seed` for initial root frontier or later unrelated user clues; use `expand` for work caused by the current popped/assigned item.
- Assigned items are in-flight, not active frontier; merge returned work with `expand --item <assigned-item>`.
- For parallel work, decompose one focus item into explicit independent sub-probes before fanout; do not assign unrelated jobs just to keep workers busy.
- The helper CLI is installed separately; if `reasoning-graph --help` is unavailable, see `docs/install.md`. Detailed mechanics: `docs/driver.md`.

## Controller-only probe delegation

For non-trivial reasoning-graph work, the main thread is a controller, not an explorer. Parent owns goal framing, canonical graph/state, frontier definition, priority, stop policy, merge decisions, and final answer.

Delegate observation-heavy work when a subagent backend is available: source research, code/file inspection, external docs lookup, hypothesis probes, evidence collection, validation checks, candidate audits, and adversarial review. Parent may do targeted inspection needed to frame probes, adjudicate conflicts, or verify high-impact child claims. If no backend is available, run bounded probes inline and keep raw observations out of final prose unless needed.

Delegation unit = bounded probe: one frontier item, hypothesis, test, source family, or candidate audit; bounded scope and stop rule; explicit output contract; no final decision authority.

Parent chooses treatment for each popped item: expand, assign async probe/verify work, rank/close, or compose these. Children return observations plus optional proposed patch/artifact. Parent reviews and applies accepted changes with `reasoning-graph expand --item <assigned-item> --patch <patch>`.

Subagent probe output should include target, evidence for/against with source refs, proposed graph nodes/edges, confidence or likelihood impact, residual uncertainty, suggested next probes, and blocked/stop reason when applicable.

## Agent schema reference

This section is the agent-facing schema reference: enough structure to build and review graph state during normal work. Keep rare, debugging-heavy, or example-heavy details in `docs/schema/`. Validate real state files with the installed JSON schemas and `reasoning-graph validate`.

Top-level state fields:

- `summary` — optional human summary of the current graph state
- `nodes` — truth-bearing graph objects: goals, evidence, constraints, assumptions, derivations, tests, candidates
- `edges` — directed relationships between nodes
- `frontier` — pending work items; lower `search_cost` pops first after sorting
- `factors` — non-independent input groups for anti-double-counting numeric belief updates
- `events` — driver audit log for init/seed/pop/assign/expand/rank/stop actions
- `goal_policy`, `goal_groups`, `stop_policy`, `branch_policy`, `search_policy` — optional control policies
- `report`, `presentation`, `view` — optional human/report/rendering metadata; source of truth remains nodes, edges, frontier, and events

Node types:

- `goal` — target to prove, solve, decide, or explain
- `evidence` — observed, given, verified, or source-backed statement; use `confidence` when observation/transcription/source reliability matters
- `constraint` — boundary valid answers must satisfy; connect with `requires`
- `derived` — conclusion from prior nodes or conditional branch reasoning
- `assumption` — uncertain branch point with numeric `prior`; keep atomic and testable
- `test` — action/check/procedure; not evidence until connected to result `evidence` or `derived` nodes
- `candidate_solution` — possible answer; must include `answer_kind` and answer an accepted goal through `candidate_solution -> goal` `answers`

Edge types:

- `requires` — hard dependency; prefer `goal -> constraint` or `candidate_solution -> constraint`
- `supports` — positive belief update for an existing target; numeric form uses `likelihood` or `likelihood_ratio > 1`
- `contradicts` — negative belief update for an existing target; numeric form uses `likelihood` or `0 < likelihood_ratio < 1`; it does not delete/disqualify the target by itself
- `prompts` — non-evidential provenance from clue/claim/branch to test or follow-up; no belief update
- `leads_to` — premise/dependency used to derive a target's base belief
- `assumes` — branch or derived node proceeds under an assumption
- `answers` — candidate satisfies a goal; must be `candidate_solution -> goal`

Direction and relation rules:

- `candidate_solution -> constraint` means the candidate must satisfy the constraint.
- `evidence -> assumption` with `supports`/`contradicts` updates belief in the assumption.
- `clue/evidence -> test` with `prompts` proposes follow-up but is not evidence for the test result.
- Use `supports`/`contradicts` for evidence updates to an existing target.
- Use `leads_to` for premises that derive a target's base belief.
- Use `requires` for hard constraints or external dependencies.
- Plain incoming numeric edges are treated as independent unless grouped by `factors`.

`factors`: non-independent input groups:

- A factor is a top-level anti-double-counting record. It says: these incoming numeric edges to the same target are related, so count them together instead of multiplying them as independent evidence.
- A factor is not a node, edge, claim, candidate, proof step, or frontier item.
- Use `factors` for shared source, duplicate observation, logical overlap, common latent cause, or repeated logs from one event.
- Do not use `factors` for independent evidence, visual grouping, non-numeric relationships, or candidate grouping.
- `leads_to` factors use `aggregation: {"kind": "joint_probability", "probability": ...}`.
- `supports`/`contradicts` factors use `aggregation: {"kind": "likelihood", "if_target_true": ..., "if_target_false": ...}`. Do not set direct factor `likelihood_ratio`.
- Ungrouped incoming edges still contribute normally.
- In `seed`/`expand` patches, use `factors` to add or replace factors by `id`; audit events are recorded automatically.
- Details and examples: `docs/schema/factors.md`.

Test result pattern:

- A `test` node is a procedure, not evidence.
- Canonical pattern: `claim --prompts--> test`, `test --leads_to--> result evidence`, `result evidence --supports|contradicts--> claim`.
- Inconclusive checks should add result evidence explaining why the check did not settle the claim.
- Details and examples: `docs/schema/tests.md`.

Candidate and goal rules:

- `candidate_solution` requires `answer_kind`.
- `answer_kind` values: `exact_answer`, `exact_method`, `method_hypothesis`, `clue_path`, `blocker`.
- For concrete solve/exact-answer goals, only `exact_answer` and `exact_method` may connect to the accepted goal.
- `method_hypothesis`, `clue_path`, and `blocker` need explicit method/clue/epistemic goals or should remain assumptions/derived nodes.
- Do not make “not solved”, “cannot establish”, or “missing dependency” a candidate for a normal solve goal. That is a stop outcome or derived blocker unless the user accepted an epistemic/negative goal.
- Use multiple `goal` nodes only when the user accepts multiple outcomes, e.g. solve, prove impossible, or conclude evidence is insufficient.
- If `goal_policy.accepted_goals` is absent, all goal nodes are acceptable destinations. `preferred_goals` affects presentation/priority, not validity.
- Details and examples: `docs/schema/goals.md`.

Report and presentation metadata:

- `report` may include readable candidate summaries, `winning_path`, `next_verification`, and candidate `path_nodes`.
- `presentation` may include curated `include_nodes`, `highlight_nodes`, `dim_nodes`, `title`, and `layout_hint`.
- Do not encode rank or viability words such as `Best`, `Second`, `viable`, or `rejected` into candidate names or node text. Rank and viability derive from graph relationships, belief/truth cost, search cost, and accepted goals.
- Details and examples: `docs/schema/reporting.md`.

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

Minimal frontier example:

```json
{
  "frontier": [{
    "id": "Q1",
    "node": "T1",
    "cost_components": {"truth": "auto", "verification": 0.2},
    "estimated_remaining_cost": 0.5
  }],
  "search_policy": {"estimated_remaining_weight": 0.5}
}
```

Details: `docs/cost-model.md`.

## Exploration rules that matter most

Input ledger essentials:

- Extract the accepted `goal` first. If multiple goals conflict, ask or state the chosen primary goal.
- Classify given/source-backed facts as `evidence`, answer boundaries as `constraint`s, and plausible interpretations as `assumption`s/frontier items. Do not turn guesses into evidence.
- Before initial frontier, one bounded context pass may add cheap source-backed evidence. After search starts, model non-trivial checks/searches/experiments as `test`/frontier work and append result evidence during `expand`.
- Mark inferred constraints as inferred in text/source; ask the user when the inference is high-impact or ambiguous.
- Keep evidence concise but separate facts that play different logical roles. Add source/confidence when reliability matters.

Branch and candidate hygiene:

- Try direct derivation only when obvious; otherwise branch from generic, atomic, testable assumptions before specializing into derived nodes or candidate solutions.
- After each expansion/probe, record implications, sibling hypotheses, cheap discriminator tests, contradiction penalties, and any answer-shaped candidate. Reopen/continue only when new evidence creates new work; score-only updates stay closed.
- Assumptions should not bundle whole answers or multiple uncertain premises. If it already answers the goal, make it a derived/candidate chain instead.
- Candidate solutions are usually conclusions of explored branches, not initial buckets. Early placeholders are valid only when user-supplied, obvious from strong direct evidence, or explicitly weak/low-priority.
- If a candidate enters frontier before support is expanded, mark it provisional and give high truth/constraint-tension cost so it cannot outrank evidence-backed branches.
- A valid `candidate_solution` reaches an accepted goal or actionable answer, satisfies known constraints, has no unresolved contradiction, and states remaining assumptions/uncertainty.
- Constraint violations should add explicit cost/blocking evidence to affected branches.
- For concrete solve goals, only `exact_answer` and `exact_method` should answer the accepted goal. Do not make “not solved” / “insufficient evidence” a candidate unless the goal is explicitly epistemic.
- Ranked report candidates must correspond to explored, tested, or evidence-penalized branches; mention unexplored alternatives as possibilities, not ranked candidates.

High-salience clue/family branching:

- Official hints, docs, maintainer comments, theorem conditions, logs, test failures, or other authoritative clues deserve interpretation branches before brute force.
- When dropping a clue family would materially change search, mark it `clue_family: true` with `salience`; cheap clue interpretations should outrank broad/brute-force probes.
- Expand coarse possibility families before micro-variants; concrete variants belong inside the popped family expansion/test.
- Failed bounded tests penalize only the exact tested interpretation, not the whole clue family. Add sibling/refined interpretations or explicit exhaustion proof.
- Partial clue/family expansion is not exhaustion: leave live child frontier, explicit `exhausted: true` with `exhaustion_reason`, or revive by adding a child branch under the original family. When continuing from reports without prior graph state, reconstruct high-salience clue families as graph nodes, not generic “prior probes failed” evidence.
- For high-salience clue/family nodes, consider distinct meaningful branches such as direct/literal, structural/transform, and low-prior wildcard. Do not invent branches to satisfy a count; if fewer are meaningful, record `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof.
- One-child expansion is allowed but should trigger a check for missed siblings before claiming exhaustion/completion.

## Stop and audit rules

Stop is metric-gated, not discretionary. A normal stop is allowed only when at least one holds:

- event-reachable frontier is exhausted
- enough viable candidates have been explored, usually `min_viable_candidates: 3` for comparison/search tasks
- strongest viable candidate crosses an explicit threshold, usually `belief_threshold: 0.8`
- explicit external budget is reached and remaining live frontier is recorded as unfinished, not exhausted

Do not stop on an epistemic/blocker candidate while meaningful answer-goal frontier remains live unless `stop_policy` explicitly allows it. For benchmark/search tasks, set or expect strict `stop_policy`: `min_viable_candidates: 3`, `belief_threshold: 0.8`, `max_live_frontier_items: 0`, `require_frontier_exhausted_for_epistemic_stop: true`, `severity: "error"`.

Other stop rules:

- Early threshold stop is allowed, but do not pad ranked candidates with unexplored alternatives.
- Trivial or directly contradicted alternatives may be closed only when likelihood/cost updates make them clearly dominated.
- Contradicted candidates may remain visible with lower belief, but should not satisfy high-confidence stop targets unless effective truth cost still passes.
- Ask user before deepening search when remaining exploration would cost meaningful time.
- Stop reasons must name the real gate: threshold met, candidate count met, frontier exhausted, budget exhausted, or blocker reached.

Before final, run driver validation/audit/stop-review mechanics in `docs/driver.md`. Treat warnings as actionable for benchmark/published artifacts: fix state/events or explain why the warning is acceptable.

## Output formats

Default final response:

1. answer/recommendation
2. concise proof path
3. key assumptions
4. top competing candidates when ambiguity matters
5. contradictions only if important
6. next test/action if uncertainty remains

Graph/HTML artifact when requested:

1. persist state JSON in the requested output path or durable artifact location; use `/tmp` only as ad hoc fallback
2. validate/audit
3. generate baseline artifact with `reasoning-graph html state.json -o <path>.html`
4. include summary, candidate table, readable evidence/constraint details, curated presentation graph, and full audit graph

Do not expose hidden chain-of-thought or raw scratch state. Provide user-facing proof path / reasoning summary.

Details: `docs/rendering.md`.

## Final checklist

- Accepted goal is explicit; evidence, constraints, assumptions, and uncertainty are separated.
- Every viable candidate answers an accepted goal, satisfies constraints, and is not a placeholder/blocker for a normal solve goal.
- Meaningful alternatives and high-salience clue families are expanded, live, contradicted, or explicitly exhausted with reason.
- Failed bounded tests penalize only affected branches; constraints add explicit cost/blocking evidence for invalid branches.
- Ranked candidates come from explored, tested, or evidence-penalized branches; unexplored alternatives are labeled as unexpanded possibilities.
- Stop follows metric-gated policy; do not hide live answer frontier behind blocker/epistemic stops.
- State is built/updated through driver events before major search moves; stopped state passes validation, audit, and semantic stop review.
- Final prose matches graph state, invents no evidence, and keeps priors/costs visible only when useful.
- Graph/HTML artifact, if requested, is generated from validated state and shows readable summary, candidates, evidence/constraints, and curated presentation graph.

## Reference docs

- `docs/schema/factors.md` — detailed `factors` examples and validation rules
- `docs/schema/goals.md` — candidate, answer-kind, hypothetical branch, and multiple-goal rules
- `docs/schema/tests.md` — detailed test lifecycle and result evidence pattern
- `docs/schema/reporting.md` — report and presentation metadata examples
- `docs/cost-model.md` — probability/cost math, likelihoods, bounded probes
- `docs/driver.md` — state JSON, helper commands, event/audit/stop-review mechanics
- `docs/rendering.md` — final prose, graph/HTML artifacts, canvas rules
- `docs/install.md` — one-time helper CLI install
- Installed package schemas (`reasoning_graph.schemas`) — machine-readable state/patch contracts. In this repository they live under `packages/reasoning-graph/src/reasoning_graph/schemas/`.
