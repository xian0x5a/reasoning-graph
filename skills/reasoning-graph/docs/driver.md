# Reasoning Graph Driver Reference

State shape, helper commands, strict driver loop, audit checks, and semantic stop review.

## Search State

For every reasoning-graph skill use, maintain explicit graph/search state. Do not dump raw state to the user unless useful or requested.

Separate graph nodes from search frontier items.

Example graph nodes:

```yaml
- id: E1
  type: evidence
  text: "The failing test is test_login_rejects_bad_token"
  source: "tests/auth_test.py::test_login_rejects_bad_token"
  prior: 0.99

- id: C1
  type: constraint
  text: "Do not change public token format"
  source: "inferred from compatibility requirement"

- id: A2
  type: assumption
  text: "The root cause is stale cache"
  prior: 0.6
  prior_reason: "Common failure mode for this symptom"
```

Example frontier item:

```yaml
- id: Q7
  node: A2
  parent: Q3
  related: [E1, C1]
  scratch:
    - "Cache branch may split into stale-read vs invalidation-order variants."
    - "If this becomes important, promote it to a derived/test node."
  step_truth_cost: 0.51
  truth_cost: 0.51
  work_cost: 0.30
  base_search_cost: 0.81
  estimated_remaining_cost: 0.40
  heuristic_cost: 0.40
  step_cost: 1.21
  search_cost: 1.21
  active_assumptions: [A2]
  evidence_version: E1
```

Do not treat a frontier item as a prewritten one-step instruction. The `node` is the thing to expand; its text is the prompt. The parent chain is the main context. Use optional `related` only for extra node IDs worth reading that are not already on the parent path. Use optional `scratch` for pre-pop inspirations/reminders; scratch is not evidence, not a constraint, and not a ranking input. If a scratch item becomes important, promote it to a real `evidence`/`derived`/`test`/`assumption` node. After popping an item, digest the node, parent path, active assumptions, related nodes, and scratch, then record the resulting child branches, tests, or contradictions.

Use parent pointers instead of copying full paths. Reconstruct a path by walking parent links.

Use an expanded ledger to avoid loops, not to erase alternatives:

```yaml
expanded:
  - signature: "node=D4|assumptions=A2,A5|evidence=E1"
    item: Q9
    search_cost: 2.1
```

Expansion signature minimum:

```txt
current_node + sorted active_assumption_ids + canonical expansion params/scope/budget
```

Guidelines:

- Skip exact cycles.
- Prefer expanding lower-cost frontier items first, best-first style.
- Use latest graph evidence when computing every active item's cost; do not include `evidence_version` in active dedupe.
- Active frontier must contain at most one item per expansion signature. If two active items have the same signature, keep the lowest current `search_cost`; ties keep the existing/earlier item.
- Do not hard-delete higher-cost or less-optimized paths solely because priors may be wrong when they represent different expansion signatures.
- Keep multiple candidate paths in the frontier when they represent meaningfully different assumption chains, answer routes, params, scopes, or budgets.
- If path-specific context should affect expansion, encode it as `active_assumptions`, a more specific child node, or explicit params/scope/budget; parent path alone is provenance, not separate live work.
- If new evidence changes likelihood updates, an explicit posterior, or frontier ordering, recompute active costs and supersede stale duplicate active items instead of carrying duplicate work.

## Helper CLI Reference

Use the helper as the search driver. The executable loop and minimal patch shape live in `../SKILL.md`; this page documents command variants, full state shape, events, and audit behavior.

Bookkeeping that does not change the search can be done directly: fixing typos, adding an obvious source field, formatting JSON, recomputing costs, validation, Mermaid/HTML generation, or writing the final report from an already-settled state. Mutating commands rewrite the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout.

```bash
reasoning-graph init --goal "Diagnose outage" --strict -o state.json
reasoning-graph doctor state.json                  # validate, summarize frontier, audit when events exist
reasoning-graph validate state.json                # schema/reference/cost sanity checks
reasoning-graph costs state.json                   # compute truth_cost/search_cost in place
reasoning-graph sort state.json                    # compute costs and sort frontier in place
reasoning-graph costs state.json -o -              # print updated state without mutating state.json
reasoning-graph costs - < state.json               # stdin input prints updated state to stdout
reasoning-graph frontier state.json       # show active frontier derived from events
reasoning-graph next state.json           # show lowest-cost active item + path context
reasoning-graph next state.json --pop  # persist init/pop event for lowest-cost item
reasoning-graph expand state.json --item Q7 --patch expansion.json  # Q7 is an example popped/assigned item id
reasoning-graph assign state.json --item Q7 --agent researcher      # record async in-flight probe work
reasoning-graph rank state.json --item Q7  # close pending item by recording current best viable candidate
reasoning-graph seed state.json --patch later-root-seed.json        # add unrelated root inspiration; requires reason after driver init
reasoning-graph stop state.json --reason "CS1 answers the goal and stop policy is satisfied" --outcome solved -o state.stopped.json
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json  # audit strict-search compact events after driver events exist
reasoning-graph stop-review state.stopped.json --draft answer.md  # final stop checklist after stop
reasoning-graph path state.json Q7        # reconstruct parent-pointer path for an item id
reasoning-graph mermaid state.json        # emit Mermaid source
reasoning-graph html state.json -o graph.html  # replace with requested/durable path; use /tmp only as ad hoc fallback
```

Use the installed `reasoning-graph` CLI. In a repository checkout, developers may run `uv --project packages/reasoning-graph run reasoning-graph ...`.

State JSON shape:

```json
{
  "summary": {
    "title": "Reasoning Graph",
    "answer": "Compact answer shown above the graph."
  },
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Solve the problem"},
    {"id": "E1", "type": "evidence", "text": "Observed failure", "source": "user prompt", "prior": 0.95},
    {"id": "C1", "type": "constraint", "text": "Must preserve API", "source": "inferred from user intent"},
    {"id": "A1", "type": "assumption", "text": "Likely route", "prior": 0.6},
    {"id": "CS1", "type": "candidate_solution", "text": "Candidate answer", "answer_kind": "exact_answer"}
  ],
  "edges": [
    {"id": "A1-CS1", "from": "A1", "to": "CS1", "type": "leads_to", "reasoning": "The target conclusion depends on this premise."},
    {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This candidate supplies the answer requested by the goal."}
  ],
  "frontier": [
    {
      "id": "Q1",
      "node": "A1",
      "parent": null,
      "cost_components": {
        "truth": "auto",
        "verification": 0.2,
        "reasoning_complexity": 0.1,
        "constraint_tension": 0
      },
      "estimated_remaining_cost": 0.5
    }
  ],
  "search_policy": {
    "estimated_remaining_weight": 1.0
  },
  "stop_policy": {
    "min_viable_candidates": 3,
    "belief_threshold": 0.8,
    "max_live_frontier_items": 0,
    "require_frontier_exhausted_for_epistemic_stop": true,
    "severity": "warning"
  },
  "branch_policy": {
    "high_salience_min_children": 3,
    "low_prior_wildcard_required": true,
    "enforce_on": "exhaustion_stop",
    "severity": "warning"
  },
  "report": {
    "candidates": [
      {
        "id": "CS1",
        "name": "Likely route",
        "belief": 0.6,
        "search_cost": 1.310826,
        "path_nodes": ["E1", "C1", "A1", "CS1"],
        "why": "Lowest explored search cost and satisfies constraints",
        "next_test": "Verify supporting evidence"
      }
    ],
    "winning_path": ["Observed failure", "Likely route", "Candidate answer"],
    "next_verification": "Verify supporting evidence"
  },
  "presentation": {
    "include_nodes": ["E1", "C1", "A1", "G1"],
    "highlight_nodes": ["A1", "G1"],
    "dim_nodes": [],
    "layout_hint": "evidence-left-candidates-right"
  },
  "events": [
    {"step": 1, "action": "init", "frontier": ["Q1"]},
    {"step": 2, "action": "pop", "item": "Q1", "cost": 1.310826},
    {"step": 3, "action": "rank", "item": "Q1", "best": "CS1", "belief": 0.6, "candidates": [{"node": "CS1", "belief": 0.6, "effective_truth_cost": 0.510826}]},
    {"step": 4, "action": "stop", "reason": "CS1 answers G1 and no live frontier remains", "outcome": "solved"}
  ],
  "view": {
    "winning_path": ["A1", "CS1", "G1"],
    "dimmed_branches": []
  }
}
```

`branch_policy.high_salience_min_children` is an audit heuristic, not a hard branch count. It asks the driver to justify narrow high-salience expansions; use `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof instead of inventing weak branches.

Cost behavior:

- `truth: "auto"` or legacy `uncertainty: "auto"` uses effective node truth cost: explicit `posterior` when present; otherwise local probability plus ungrouped incoming `leads_to` premise costs and `leads_to` factor joint-probability costs, then ungrouped `supports`/`contradicts` likelihood updates and grouped factor likelihood updates.
- `truth_cost` is the current node's effective truth cost. `step_truth_cost` is kept as a legacy mirror of `truth_cost`.
- `work_cost` is local remaining work/risk for this next expansion: verification, effort budget, reasoning complexity, and constraint tension.
- `base_search_cost` is `truth_cost + work_cost` before goal-distance heuristics.
- `estimated_remaining_cost` is optional top-level heuristic remaining work.
- Put remaining-cost fields on the frontier item itself, not inside `cost_components`.
- `step_cost` and `search_cost` are the frontier priority score: `base_search_cost + weighted estimated_remaining_cost`. Parent pointers do not accumulate cost; past work is sunk.
- Numeric cost inputs and computed search costs must be finite and non-negative. Likelihood ratios must be finite and positive, including ratios derived from likelihood probabilities and updates on nodes with posterior overrides. Invalid numbers and arithmetic overflow are rejected; JSON output never emits `NaN` or `Infinity`.
- `sort` keeps all frontier ledger items but orders them by ascending `search_cost`; it is optional before `next` because `next` computes costs and sorts active items internally.
- `frontier` derives the currently active virtual frontier from `events`, including `supersede` removals and assigned in-flight probes. Without strict events, older loose states expose stored frontier items for compatibility.
- `next --pop` computes current costs, sorts active items internally, appends a deduped `init` when needed, keeps one item per expansion signature, then a `pop` event for the lowest-cost active item. If a popped item has not been expanded/assigned/ranked, `next --pop` refuses to continue.
- `assign --item Q7` records a pending popped item as async in-flight probe work and clears the pending slot so the driver may pop more eligible work. Assigning additional async work is blocked at the concurrency budget. Default max concurrency is 3 unless `search_policy.max_probe_concurrency` or `--max-concurrency` says otherwise.
- `seed --patch seed.json` adds root frontier items. Before driver init it bootstraps initial work without an event; after driver init it appends a `seed` event and requires patch `reason`. Use this for unrelated user clues or random inspirations, not for child work caused by a popped item.
- `expand --patch` appends new nodes/edges/frontier items and records one `expand` event for the pending popped item or an in-flight assigned item. Duplicate active expansion signatures are deduped using latest `search_cost`; lower-cost new duplicates supersede older active items, while higher/equal-cost new duplicates are skipped.
- Use patch `update_nodes` for existing node field changes. `nodes` is insert-only and duplicate ids are rejected. `update_nodes` entries are explicit top-level field replacements and require existing node ids, e.g. `{"update_nodes": [{"id": "A1", "set": {"posterior": 0.72}}]}`. The generated expand event records `updated_nodes` with changed field names.
- `path` reconstructs a proof/search path from parent pointers.
- `audit` replays graph changes before each pop, then checks compact strict-search events for coherent best-first expansion. Later evidence can reorder remaining work, but cannot retroactively justify an earlier skipped cheaper item.

Expansion patch shape:

```json
{
  "summary": "Split the 74-byte clue into coarse container-format families.",
  "nodes": [
    {"id": "A8", "type": "assumption", "text": "WebCrypto AES-GCM layout family", "prior": 0.45},
    {"id": "A9", "type": "assumption", "text": "libsodium/secretbox layout family", "prior": 0.2}
  ],
  "update_nodes": [
    {"id": "A4", "set": {"posterior": 0.62}}
  ],
  "edges": [
    {"id": "E20", "from": "A8", "to": "A4", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."},
    {"id": "E21", "from": "A9", "to": "A4", "type": "supports", "reasoning": "The observed signal is more likely when the target claim is true."}
  ],
  "frontier": [
    {
      "id": "Q8",
      "node": "A8",
      "related": ["E1"],
      "scratch": ["Phrase length may matter, but branch container formats before committing."],
      "cost_components": {"truth": "auto", "verification": 0.4}
    },
    {
      "id": "Q9",
      "node": "A9",
      "related": ["E1"],
      "cost_components": {"truth": "auto", "verification": 0.5}
    }
  ]
}
```

`expand` fills missing child `parent` fields with the popped item id and records audit metadata automatically. In patch input, use `factors` to add or replace factors by id; detailed factor shapes live in `docs/schema/factors.md`. Stop events must include structured `outcome`. For high-salience branch policy, record `under_branching_reason` or `existing_sibling_frontier` when a narrow expansion is justified by the rules in `SKILL.md`.

## Driver Loop

The driver loop is required for reasoning-graph skill use. It uses a compact `events` log plus `next --pop` / `assign` / `expand` commands so the graph controls the next work item before the agent reasons. This reduces post-hoc graph decoration and makes the search trace auditable.

Do not include full frontier before/after snapshots; state already stores frontier items. Events record only search deltas:

```json
"events": [
  {"step": 1, "action": "init", "frontier": ["Q1", "Q2", "Q3"]},
  {"step": 2, "action": "pop", "item": "Q1", "cost": 1.15},
  {"step": 3, "action": "assign", "item": "Q1", "agent": "researcher", "run_id": "child-1", "max_concurrency": 3},
  {"step": 4, "action": "pop", "item": "Q2", "cost": 1.3},
  {"step": 5, "action": "assign", "item": "Q2", "agent": "scout", "run_id": "child-2", "max_concurrency": 3},
  {
    "step": 6,
    "action": "expand",
    "item": "Q1",
    "summary": "Generated coarse sibling explanations and cheap discriminator tests.",
    "add_nodes": ["A4", "A5", "T2"],
    "add_edges": ["E1", "E2"],
    "add_frontier": ["Q4", "Q5"],
    "updated_nodes": [{"id": "A1", "fields": ["posterior"]}],
    "updated_node_snapshots": [{"id": "A1", "before": {"id": "A1", "type": "assumption", "prior": 0.6}}],
    "no_new_work_reason": "A1 score changed, but no new A1-local work was implied."
  },
  {"step": 7, "action": "expand", "item": "Q2", "add_nodes": [], "add_edges": [], "add_frontier": [], "no_new_work_reason": "scout found no new local constraints"},
  {"step": 8, "action": "rank", "best": "CS1", "belief": 0.91, "candidates": [{"node": "CS1", "belief": 0.91, "effective_truth_cost": 0.094311}]},
  {"step": 9, "action": "stop", "reason": "three viable candidates compared; CS1 satisfies the accepted goal above threshold", "outcome": "candidate_count_met"}
]
```

Allowed actions:

- `init` — initial active frontier item ids after expansion-signature dedupe
- `pop` — selected lowest-cost frontier item
- `assign` — pending popped item delegated to async probe/verification work; fields: `item`, optional `agent`, `run_id`, `probe`, `concurrency_group`, `max_concurrency`, `reason`. Assigned items are in-flight, not active frontier.
- `expand` — nodes/edges/frontier items created from the popped or assigned item. Add an outgoing edge from the item node to at least one new test/result/child node when new nodes are added so the graph topology shows the exploration, not only the event log. Under strict policy a `test` expansion must add a `leads_to` result node (`docs/schema/tests.md`), and an expansion with no new frontier item and no candidate must carry `no_new_work_reason` or `under_branching_reason`. For partial high-salience family/clue expansion, prefer named child frontier items or explicit justification fields per `SKILL.md`. Do not re-queue the same parent as a substitute for naming the next probe; create a `test`/`assumption` child for the unknown instead. Optional `mode`/`summary` fields may describe the expansion, but they are not controlled vocabulary.
- `supersede` — retire an active frontier item because another active item has the same expansion signature and lower current `search_cost`; fields: `item`, `replacement`, `reason`
- `rank` — current best viable `candidate_solution` derived from graph belief; optional `item` closes a pending popped item
- `stop` — terminal event; must include `outcome` enum (`solved`, `candidate_threshold_met`, `candidate_count_met`, `frontier_exhausted`, `budget_exhausted`, `blocked`, `user_stopped`, `inconclusive`)

Ending commands:

- `stop` ranks the current best viable `candidate_solution` for candidate-bearing outcomes (`solved`, `candidate_threshold_met`, `candidate_count_met`), then writes the terminal event. It is rejected while any accepted, non-optional goal is unanswered (`docs/schema/goals.md`).
- `--force` on `expand`/`assign` skips ordering and concurrency policy guards only; driver init, an existing frontier item, and a prior pop are always required, so a forced command cannot persist a structurally invalid trace.
- For non-candidate outcomes, `stop` only writes the terminal event.

### Semantic Stop Review

Policy semantics live in `SKILL.md`; this section covers the CLI stop, validation, audit, and reviewer mechanics.

Stop is two gates:

Stop reasons must state the real stopping condition: threshold met, required candidate count met, frontier exhausted, budget exhausted, or blocker reached. Do not use tautologies like “best candidate has highest belief”; ranking already guarantees that.

1. `reasoning-graph stop ... -o state.stopped.json` appends rank/stop events for candidate-bearing outcomes without mutating the working state; then run `validate`/`audit` on `state.stopped.json`.
2. A semantic reviewer approves `state.stopped.json` before it is promoted.

If gate 1 fails, continue/repair search. If gate 2 fails, discard the stopped candidate and continue/repair. Bound retries to one reviewer repair pass unless the user asked for exhaustive work.

Prefer a fresh reviewer agent; otherwise switch roles. Reviewer reads the user request, stopped candidate state, original state if needed, and final answer draft. Do not solve from scratch except to check obvious missed contradictions or live branches.

Reviewer output:

```yaml
verdict: pass | fail
required_fixes: []
semantic_tricks_checked: []
notes: []
```

Required checks:

- stop outcome/reason matches accepted goal, derived best candidate, and stop policy
- no meaningful answer-goal frontier remains hidden behind an epistemic/blocker stop
- high-salience clue/family nodes are expanded, live, or explicitly exhausted
- best candidate answers the goal, satisfies constraints, and is not a placeholder/duplicate/non-answer
- every accepted goal is answered, and `summary.answer`, `report.answer`, and the draft name the best candidate of each accepted goal by id or exact text
- blockers are not disguised as answer candidates for normal solve goals
- failed broad tests do not erase untested sibling interpretations or parent clue families
- contradictions/failures penalize only affected branches
- final answer draft matches graph state and invents no new evidence

Do not call `next --pop` again until the pending popped item is expanded, assigned, or ranked. Every `stop` requires no pending item; candidate-bearing `stop` auto-ranks only after terminal preflight passes. Assigned items may complete out of pop order, but stop is invalid while any assigned item remains in-flight. A one-child expansion is allowed when no useful sibling branch comes to mind; audit treats it as a soft warning to reconsider branching, not a failure.

Before final, validate, audit, and semantically review the stopped state:

```bash
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json
reasoning-graph stop-review state.stopped.json --draft answer.md
```

Treat audit/stop-review warnings as actionable for benchmark/published artifacts. Either fix the state/events or explicitly explain why the warning is acceptable. In particular, if audit warns that `candidate_solution` nodes were not added or ranked by driver events, do one of these before final:

- add proper `expand`/`rank`/contradiction-penalty events for those candidates,
- demote them to assumptions/derived notes if they were only speculative ideas,
- or keep them out of `nodes` and mention them as unexpanded possibilities in prose/report metadata.

Do not call a strict trace clean while leaving unexplored candidate nodes that only decorate the final graph.

Audit checks:

- steps strictly increase
- `init` appears before search events
- `pop` item is currently in virtual frontier
- popped item has lowest current `search_cost`
- `assign` follows the current pending pop and respects declared max concurrency
- `expand` follows the pending pop or targets an in-flight assigned item
- `add_frontier` items exist and usually parent to expanded item
- expansions whose popped graph node has no outgoing edge to added nodes get a soft trace-topology warning
- one-child non-terminal expansions get a soft under-branching warning only when the final stop claims exhaustion/completion, unless `under_branching_reason` or `existing_sibling_frontier` is recorded
- high-salience clue/family expansions below `branch_policy.high_salience_min_children` warn/fail on exhaustion/completion stops unless they include `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof; set `branch_policy.enforce_on: "always"` for noisy development audits
- candidate solutions contradicted by evidence remain nodes but should not satisfy belief/threshold targets unless their effective truth cost still passes
- `rank.best`, `rank.belief`, and `rank.candidates` rows match the values derived from the graph as it stood at rank time
- each node, edge, and frontier item is claimed as added by at most one event
- under strict policy, `test` expansions record a `leads_to` result and zero-work expansions record a reason
- candidate-bearing `stop` outcomes leave no accepted, non-optional goal unanswered
- `stop` has a reason
- `audit` and `doctor` print `peak_live_frontier`, the largest active frontier reached during replay; peak 1 on a task with competing interpretations means the graph was not exercised
- pop costs and remaining-frontier order are evaluated against graph evidence available before each pop; CLI-generated node/factor update snapshots make mutable replacements replayable

Limit: the driver loop still cannot prove hidden cognition used best-first ordering; it makes the external search trace auditable and catches incoherent post-hoc traces. The `next --pop` / `assign` / `expand` loop reduces post-hoc decoration by making the graph control the next work item before the agent reasons or uses tools.
