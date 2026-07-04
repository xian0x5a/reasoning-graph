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

## Mode selection

- **Compact mode:** small/direct tasks where a short answer plus visible proof path is enough. No state file required.
- **Driver mode:** multi-branch, uncertain, benchmark, artifact-producing, or high-stakes reasoning where search order and stop conditions need auditability. Use the `reasoning-graph` CLI state, frontier, audit, and stop-review.
- If unsure, start compact; switch to driver mode when alternatives multiply, evidence conflicts, or stopping needs a measurable rule.

## Controller-only probe delegation

For non-trivial reasoning-graph work, the main thread is a controller, not an explorer. The parent owns goal framing, canonical graph/state, branch/frontier definition, priority, stop policy, merge decisions, and final answer.

Delegate observation-heavy work when a subagent backend is available:

- source research
- codebase/file inspection
- external documentation lookup
- hypothesis probes
- evidence collection
- validation checks
- candidate audits
- adversarial review

Do not let the parent do broad research, large file inspection, or detailed verification when a child can do it. This protects main-thread context from raw evidence noise. Parent may do targeted inspection needed to frame probes, adjudicate conflicts, or verify high-impact child claims. Simple answer-only tasks, trivial bookkeeping, and unavailable delegation backends are exceptions. If no subagent backend is available, run bounded probes inline and keep raw observations out of the final answer unless needed.

Delegation unit = bounded probe:

- one frontier item, hypothesis, test, source family, or candidate audit
- bounded scope and stop rule
- explicit output contract
- no final decision authority

The frontier driver (`sort`/`next`) chooses the next focus item. Parent chooses treatment: expand, assign async probe/verify work, close, or a mix. Subagents collect observations. Parent updates graph and decides.

Frontier treatments may compose:

- probe first when expansion needs missing context
- expand first when probe targets are unclear
- probe several child branches in parallel after expansion
- verify after probe results support a candidate
- create follow-up frontier items from any result

Parent owns the treatment decision and records why when the choice is non-obvious. Subagents do observation-heavy probe/verify work; parent handles graph structure, merge, priority, and final judgment. Use async subagents for independent probes. Default max concurrency is 3 unless top-level `search_policy.max_probe_concurrency` or explicit `reasoning-graph assign --max-concurrency` overrides it.

Subagent probe output should include:

- probe target
- evidence found with source/file refs
- evidence against the target
- proposed graph nodes/edges
- confidence or likelihood impact
- residual uncertainty
- suggested next probes
- blocked/stop reason when applicable

Children must not decide the final answer or mutate canonical graph state. Child returns observations and optional proposed patch/artifact; parent reviews and applies accepted changes with `reasoning-graph expand --item <assigned-item> --patch <patch> -i`. When generic orchestration mechanics matter, use the available subagent system; this skill defines how delegation maps onto reasoning-graph probes.

## Core operating loop

1. **Frame goal.** Identify accepted goal(s). If the user only asked to solve, use one `goal`; add epistemic/blocker goals only when accepted by user or task wording.
2. **Extract ledger.** Separate given/source-backed `evidence`, hard `constraint`s, and uncertain `assumption`s. Do not treat plausible interpretations as evidence.
3. **Initialize frontier.** From a fresh `init` state, write a seed patch with initial evidence/constraints/assumptions/tests and root frontier items, then run `reasoning-graph seed state.json --patch seed.json -i`. Initial seed should happen before first `next --pop`; seed frontier items must not fake parent refs.
4. **Pop focus.** In driver mode, run `reasoning-graph sort state.json -i` and `reasoning-graph next state.json --pop -i` before major search, test, file inspection, verification, or branch-selection work.
5. **Choose treatment.** Decide whether the popped item needs expansion, async probe assignment, verification, closure/deprioritization, or a composed treatment. Use subagents for observation-heavy probe/verify work.
6. **Assign or update.** For async work, run `reasoning-graph assign state.json --item Q7 -i`, launch the child, then continue popping eligible work; assigning more async work is blocked at the concurrency limit. For immediate work or returned child results, merge only reviewed findings/expansions into nodes, edges, costs, and frontier changes. Use `reasoning-graph seed` for later root inspirations or new user clues unrelated to the current popped item; include `reason` after driver init. Reject unsupported claims and calibrate `supports`/`contradicts` likelihoods or explicit posterior.
7. **Re-rank frontier.** Sort after every meaningful update.
8. **Stop by policy.** Stop only when frontier is exhausted, enough viable candidates exist, a candidate crosses threshold, budget is hit, or a real blocker is proved.
9. **Review final.** Validate/audit state, then ensure final prose matches graph and invents no evidence.

## Agent schema reference

This section is the agent-facing schema reference: enough structure to build and review graph state during normal work. Keep rare, debugging-heavy, or example-heavy details in `docs/schema/`. Validate real state files with the installed JSON schemas and `reasoning-graph validate`.

Top-level state fields:

- `summary` — optional human summary of the current graph state
- `nodes` — truth-bearing graph objects: goals, evidence, constraints, assumptions, derivations, tests, candidates
- `edges` — directed relationships between nodes
- `frontier` — pending work items; lower `search_cost` pops first after sorting
- `factors` — non-independent input groups for anti-double-counting numeric belief updates
- `events` — driver-mode audit log for init/seed/pop/assign/expand/rank/stop actions
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

## Helper commands

The skill directory contains instructions only; the helper CLI is installed separately. If `reasoning-graph --help` is unavailable, install it with:

```bash
uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

Then run `reasoning-graph ...`. In a repository checkout, developers may use `uv --project packages/reasoning-graph run reasoning-graph ...` instead.

```bash
reasoning-graph init --goal "Diagnose outage" --strict -o state.json
cat > seed.json <<'JSON'
{
  "nodes": [
    {"id": "E1", "type": "evidence", "text": "Initial observed fact", "confidence": 0.9},
    {"id": "A1", "type": "assumption", "text": "Plausible cause to test", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Check the plausible cause"}
  ],
  "edges": [
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 2.0},
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"}
  ],
  "frontier": [{"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.1}}]
}
JSON
reasoning-graph seed state.json --patch seed.json -i
reasoning-graph doctor state.json
reasoning-graph validate state.json
reasoning-graph costs state.json -i
reasoning-graph sort state.json -i
reasoning-graph frontier state.json
reasoning-graph next state.json --pop -i
cat > expansion.json <<'JSON'
{"no_new_work_reason": "Initial test queued; stop this smoke run before adding real follow-up branches."}
JSON
reasoning-graph expand state.json --item Q1 --patch expansion.json -i
reasoning-graph stop state.json --reason "Smoke run reached the first seeded test and stopped by user request" --outcome user_stopped -o state.stopped.json
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json
reasoning-graph stop-review state.stopped.json
reasoning-graph mermaid state.stopped.json > graph.mmd
reasoning-graph html state.stopped.json -o graph.html
```

Do not call `next --pop` again until the pending popped item is recorded through `expand`, `assign`, or `rank`. Candidate-bearing `stop` auto-ranks and may close a pending item; non-candidate `stop` requires no pending item. Use `seed` for root frontier items: initial bootstrap before driver events, or later unrelated root inspirations with patch `reason`; use `expand` for work caused by the current popped/assigned item. If delegating, record the popped item with `assign`, launch async work, and merge the returned result later with `expand --item <assigned-item>`. For parallel work, prefer decomposing one focus item into explicit independent sub-probes before fanout; do not assign unrelated jobs just to keep workers busy unless each assignment is recorded in state and concurrency remains within budget.

Details: `docs/driver.md`.

## Expansion rules that matter most

- Assumptions should be atomic/testable, not answer-shaped bundles.
- Candidate solutions are usually conclusions of explored branches, not initial buckets.
- For concrete solve goals, only `exact_answer` and `exact_method` should answer accepted goal.
- Do not make “not solved” / “insufficient evidence” a candidate unless goal is explicitly epistemic.
- Authoritative clues deserve interpretation branches before broad brute-force branches.
- Failed bounded tests penalize exact tested interpretation, not whole clue family.
- High-salience clue/family expansions should consider multiple distinct interpretations, such as direct/literal, structural/transform, or low-prior wildcard when meaningful. Do not invent branches to satisfy a count; if only one or two meaningful branches exist, record `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof.

Details: `docs/exploration.md`.

## Stop and audit rules

Default stopping must be metric-gated, not discretionary. Normal stop is allowed when at least one is true:

- event-reachable frontier exhausted
- enough viable candidates explored, usually `min_viable_candidates: 3` for comparisons
- strongest viable candidate crosses explicit threshold, e.g. `belief_threshold: 0.8`
- external budget reached and remaining live frontier is recorded as unfinished

For benchmark/search tasks, prefer this top-level state config. The strict `init` profile already includes similar defaults.

```json
"stop_policy": {
  "min_viable_candidates": 3,
  "belief_threshold": 0.8,
  "max_live_frontier_items": 0,
  "require_frontier_exhausted_for_epistemic_stop": true,
  "severity": "error"
}
```

Before final in driver mode, validate/audit the stopped state and run semantic stop-review:

```bash
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json
reasoning-graph stop-review state.stopped.json --draft answer.md
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

1. persist state JSON in the requested output path or durable artifact location; use `/tmp` only as ad hoc fallback
2. validate/audit
3. generate baseline artifact with `reasoning-graph html state.json -o <path>.html`
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
- Stopped state semantically reviewed before final, if driver mode was used?
- Graph HTML, if requested, generated from validated state with helper?

## Reference docs

- `docs/schema/factors.md` — detailed `factors` examples and validation rules
- `docs/schema/goals.md` — candidate, answer-kind, hypothetical branch, and multiple-goal rules
- `docs/schema/tests.md` — detailed test lifecycle and result evidence pattern
- `docs/schema/reporting.md` — report and presentation metadata examples
- `docs/cost-model.md` — probability/cost math, likelihoods, bounded probes
- `docs/exploration.md` — ledger extraction, branching, stopping, candidate hygiene
- `docs/driver.md` — state JSON, helper commands, event/audit semantics
- `docs/rendering.md` — compact output, graph mode, HTML/canvas rules
- Installed package schemas (`reasoning_graph.schemas`) — machine-readable state/patch contracts. In this repository they live under `packages/reasoning-graph/src/reasoning_graph/schemas/`.
