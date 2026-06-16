# Reasoning Graph Driver Reference

State shape, helper commands, strict driver loop, audit checks, and semantic stop review.

## Search State

For complex tasks or graph mode, maintain explicit graph/search state in scratch notes. Do not dump raw state to the user unless useful or requested.

Separate graph nodes from search frontier items.

Example graph nodes:

```yaml
- id: E1
  type: evidence
  text: "The failing test is test_login_rejects_bad_token"
  source: "tests/auth_test.py::test_login_rejects_bad_token"
  confidence: 0.99

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

Do not treat a frontier item as a prewritten one-step instruction. The `node` is the thing to expand; its text is the prompt. The parent chain is the main context. Use optional `related` only for extra node IDs worth reading that are not already on the parent path. Use optional `scratch` for pre-pop inspirations/reminders; scratch is not evidence, not a constraint, and not a ranking input. If a scratch item becomes important, promote it to a real `evidence`/`derived`/`test`/`assumption` node. After popping an item, digest the node, parent path, active assumptions, related nodes, and scratch, then generate multiple meaningful child branches, tests, or contradictions.

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

## Helper Script and Driver

For complex reasoning, use the helper as the search driver. The graph should choose the next work item before major search moves: substantial reasoning, branch selection, evidence-gathering tool use, searches, or tests. Skip the driver when the task is small enough that graph overhead would dominate, or when doing bookkeeping that does not change the search.

Use the helper for graph mode, multi-branch reasoning, frontier ranking, path reconstruction, and auditable artifacts. Bookkeeping can be done directly: fixing typos, adding an obvious source field, formatting JSON, recomputing costs, validation, Mermaid/HTML generation, or writing the final report from an already-settled state.

```bash
uv run rg template strict -o state.json      # emit starter state profile
uv run rg init --goal "Diagnose outage" --strict -o state.json
uv run rg doctor state.json                  # validate, summarize frontier, audit when events exist
uv run rg stop-review state.json --draft answer.md  # final stop checklist
uv run rg validate state.json                # schema/reference/cost sanity checks
uv run rg costs state.json                   # compute truth_cost/search_cost
uv run rg audit state.json          # audit strict-search compact events
uv run rg sort state.json           # compute costs and sort frontier by search_cost
uv run rg sort state.json -i        # rewrite state.json sorted in place
uv run rg frontier state.json       # show active frontier derived from events
uv run rg next state.json           # show lowest-cost active item + path context
uv run rg next state.json --pop -i  # persist init/pop event for lowest-cost item
uv run rg expand state.json --item Q7 --patch expansion.json -i
uv run rg finalize state.json --reason "CS1 answers the goal and stop policy is satisfied" --outcome solved -o state.stopped.json
uv run rg path state.json Q7        # reconstruct parent-pointer path
uv run rg mermaid state.json        # emit Mermaid source
uv run rg html state.json -o /tmp/reasoning-graph-example.html
```

Run commands with `uv run rg` from the repo root or skill directory so dependencies come from `uv.lock`.

State JSON shape:

```json
{
  "summary": {
    "title": "Reasoning Graph",
    "answer": "Compact answer shown above the graph."
  },
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Solve the problem"},
    {"id": "E1", "type": "evidence", "text": "Observed failure", "source": "user prompt", "confidence": 0.95},
    {"id": "C1", "type": "constraint", "text": "Must preserve API", "source": "inferred from user intent"},
    {"id": "A1", "type": "assumption", "text": "Likely route", "prior": 0.6},
    {"id": "CS1", "type": "candidate_solution", "text": "Candidate answer", "answer_kind": "exact_answer"}
  ],
  "edges": [
    {"from": "A1", "to": "CS1", "type": "leads_to"},
    {"from": "CS1", "to": "G1", "type": "answers"}
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

Cost behavior:

- `truth: "auto"` or legacy `uncertainty: "auto"` uses effective node truth cost: explicit `posterior` when present; otherwise local probability plus ungrouped incoming `leads_to` premise costs and `leads_to` factor joint-probability costs, then ungrouped `supports`/`contradicts` likelihood updates and grouped factor likelihood updates.
- `truth_cost` is the current node's effective truth cost. `step_truth_cost` is kept as a legacy mirror of `truth_cost`.
- `work_cost` is local remaining work/risk for this next expansion: verification, effort budget, reasoning complexity, and constraint tension.
- `base_search_cost` is `truth_cost + work_cost` before goal-distance heuristics.
- `estimated_remaining_cost` is optional top-level heuristic remaining work.
- Put remaining-cost fields on the frontier item itself, not inside `cost_components`.
- `step_cost` and `search_cost` are the frontier priority score: `base_search_cost + weighted estimated_remaining_cost`. Parent pointers do not accumulate cost; past work is sunk.
- `sort` keeps all frontier ledger items but orders them by ascending `search_cost`.
- `frontier` derives the currently active virtual frontier from `events`, including `supersede` removals. Without strict events, older loose states expose stored frontier items for compatibility.
- `next --pop -i` appends a deduped `init` when needed, keeping one item per expansion signature, then a `pop` event for the lowest-cost active item. If a popped item has not been expanded/ranked, `next --pop` refuses to continue.
- `expand --patch` appends new nodes/edges/frontier items and records one `expand` event for the pending popped item. Duplicate active expansion signatures are deduped using latest `search_cost`; lower-cost new duplicates supersede older active items, while higher/equal-cost new duplicates are skipped.
- `path` reconstructs a proof/search path from parent pointers.
- `audit` checks compact strict-search events for coherent best-first expansion.

Expansion patch shape:

```json
{
  "summary": "Split the 74-byte clue into coarse container-format families.",
  "nodes": [
    {"id": "A8", "type": "assumption", "text": "WebCrypto AES-GCM layout family", "prior": 0.45},
    {"id": "A9", "type": "assumption", "text": "libsodium/secretbox layout family", "prior": 0.2}
  ],
  "edges": [
    {"id": "E20", "from": "A8", "to": "A4", "type": "supports"},
    {"id": "E21", "from": "A9", "to": "A4", "type": "supports"}
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

`expand` fills missing child `parent` fields with the popped item id and records `add_nodes`, `add_edges`, `add_frontier`, `update_factors`, and legacy `update_premise_groups` ids for appended or replaced objects. Use `finalize` when ending search; it records the current best viable `candidate_solution` derived from graph belief when the outcome needs a candidate, then appends the stop event. Low-level `rank` and `stop` remain available for unusual manual traces. Stop events must include structured `outcome`: `solved`, `candidate_threshold_met`, `candidate_count_met`, `frontier_exhausted`, `budget_exhausted`, `blocked`, `user_stopped`, or `inconclusive`. Expansion events may include `under_branching_reason` and `existing_sibling_frontier` when a high-salience branch legitimately adds fewer children than the branch policy floor.

An expansion patch can add or replace non-independent factors after the relevant relation edges already exist or are included in the same patch. To append a newly discovered input to an existing factor, submit the full replacement factor with the expanded `inputs` list and recalibrated aggregation:

```json
{
  "edges": [
    {"id": "E31", "from": "B1", "to": "D1", "type": "leads_to"}
  ],
  "update_factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "D1",
      "inputs": ["A1", "B1"],
      "aggregation": {"kind": "joint_probability", "probability": 0.72},
      "reason": "A1 and B1 share the same source."
    }
  ]
}
```

## Graph Driver Mode

Graph driver mode is the default for complex reasoning. It uses a compact `events` log plus `next --pop` / `expand` commands so the graph controls the next work item before the agent reasons. This reduces post-hoc graph decoration and makes the search trace auditable.

Do not include full frontier before/after snapshots; state already stores frontier items. Events record only search deltas:

```json
"events": [
  {"step": 1, "action": "init", "frontier": ["Q1", "Q2", "Q3"]},
  {"step": 2, "action": "pop", "item": "Q1", "cost": 1.15},
  {
    "step": 3,
    "action": "expand",
    "item": "Q1",
    "summary": "Generated coarse sibling explanations and cheap discriminator tests.",
    "add_nodes": ["A4", "A5", "T2"],
    "add_edges": ["E1", "E2"],
    "add_frontier": ["Q4", "Q5"],
    "updated_nodes": [{"id": "A1", "fields": ["posterior"]}],
    "no_new_work_reason": "A1 score changed, but no new A1-local work was implied."
  },
  {"step": 4, "action": "rank", "best": "CS1", "belief": 0.91, "candidates": [{"node": "CS1", "belief": 0.91, "effective_truth_cost": 0.094311}]},
  {"step": 5, "action": "stop", "reason": "three viable candidates compared; CS1 satisfies the accepted goal above threshold", "outcome": "candidate_count_met"}
]
```

Allowed actions:

- `init` — initial active frontier item ids after expansion-signature dedupe
- `pop` — selected lowest-cost frontier item
- `expand` — nodes/edges/frontier items created from the popped item. Add an outgoing edge from the popped node to at least one new test/result/child node so the graph topology shows the exploration, not only the event log. For partial family/clue expansion, add child branch nodes and frontier items for remaining live interpretations; use the same popped node again only as a temporary continuation when no child branch can yet be named. Optional `mode`/`summary` fields may describe the expansion, but they are not controlled vocabulary.
- `supersede` — retire an active frontier item because another active item has the same expansion signature and lower current `search_cost`; fields: `item`, `replacement`, `reason`
- `rank` — current best viable `candidate_solution` derived from graph belief; optional `item` closes a pending popped item
- `stop` — why search stopped; must include `outcome` enum (`solved`, `candidate_threshold_met`, `candidate_count_met`, `frontier_exhausted`, `budget_exhausted`, `blocked`, `user_stopped`, `inconclusive`)

Driver loop for search moves:

```bash
uv run rg frontier state.json
uv run rg next state.json --pop -i
# inspect popped node, parent path, active assumptions, and related nodes
# write expansion.json containing coarse child branches/tests/evidence
uv run rg expand state.json --item Q7 --patch expansion.json -i
uv run rg finalize state.json --reason "CS1 answers the goal and stop policy is satisfied" --outcome solved -o state.stopped.json
uv run rg validate state.stopped.json
uv run rg audit state.stopped.json
# semantic-review stopped candidate; promote only on pass
cp state.stopped.json state.json
uv run rg frontier state.json
```

### Semantic Stop Review

Stop is two gates:

Stop reasons must state the real stopping condition: threshold met, required candidate count met, frontier exhausted, budget exhausted, or blocker reached. Do not use tautologies like “best candidate has highest belief”; ranking already guarantees that.

1. `uv run rg finalize ... -o state.stopped.json` appends rank/stop events without mutating the working state; then run `validate`/`audit` on `state.stopped.json`.
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
- blockers are not disguised as answer candidates for normal solve goals
- failed broad tests do not erase untested sibling interpretations or parent clue families
- contradictions/failures penalize only affected branches
- final answer draft matches graph state and invents no new evidence

Do not call `next --pop` again until the pending popped item is expanded, ranked, or intentionally stopped. A one-child expansion is allowed when no useful sibling branch comes to mind; audit treats it as a soft warning to reconsider branching, not a failure.

Before final in driver mode, run:

```bash
uv run rg audit state.json
```

Treat audit warnings as actionable for benchmark/published artifacts. Either fix the state/events or explicitly explain why the warning is acceptable. In particular, if audit warns that `candidate_solution` nodes were not added or ranked by driver events, do one of these before final:

- add proper `expand`/`rank`/contradiction-penalty events for those candidates,
- demote them to assumptions/derived notes if they were only speculative ideas,
- or keep them out of `nodes` and mention them as unexpanded possibilities in prose/report metadata.

Do not call a strict trace clean while leaving unexplored candidate nodes that only decorate the final graph.

Audit checks:

- steps strictly increase
- `init` appears before search events
- `pop` item is currently in virtual frontier
- popped item has lowest current `search_cost`
- `expand` follows the most recent pop
- `add_frontier` items exist and usually parent to expanded item
- expansions whose popped graph node has no outgoing edge to added nodes get a soft trace-topology warning
- one-child non-terminal expansions get a soft under-branching warning only when the final stop claims exhaustion/completion, unless `under_branching_reason` or `existing_sibling_frontier` is recorded
- high-salience clue/family expansions below `branch_policy.high_salience_min_children` warn/fail on exhaustion/completion stops unless they include `under_branching_reason`, `existing_sibling_frontier`, or exhaustion proof; set `branch_policy.enforce_on: "always"` for noisy development audits
- candidate solutions contradicted by evidence remain nodes but should not satisfy belief/threshold targets unless their effective truth cost still passes
- `rank.best` matches the derived highest-belief viable `candidate_solution`
- `stop` has a reason

Limit: driver mode still cannot prove hidden cognition used best-first ordering; it makes the external search trace auditable and catches incoherent post-hoc traces. The `next --pop` / `expand` loop reduces post-hoc decoration by making the graph control the next work item before the agent reasons or uses tools.
