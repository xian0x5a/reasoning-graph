# Reasoning Graph Schema Reference

Canonical node, edge, factor, goal, and report metadata rules.

## Core Model

### Node Types

Use this canonical set:

- `goal` — target to prove, solve, decide, or explain
- `evidence` — observed, given, verified, or source-backed statement; may support or contradict other nodes via edges
- `constraint` — boundary that valid answers must satisfy; constraints add cost or block goal satisfaction when explicitly required
- `derived` — conclusion derived from prior nodes
- `assumption` — uncertain branch point with a numeric prior
- `test` — action, experiment, check, or evidence-gathering step; use `status` to distinguish proposed checks from performed ones
- `candidate_solution` — possible answer under current assumptions; must connect to a goal with `answers` and include `answer_kind`.

### Edge Types

Use this canonical set:

- `requires` — hard dependency; when involving constraints, prefer `goal -> constraint` or `candidate/branch -> constraint`, not `constraint -> goal`
- `supports` — positive evidence update or soft reason in favor; numeric updates use `likelihood` or `likelihood_ratio > 1`
- `assumes` — branch proceeds under an assumption
- `contradicts` — negative evidence update; numeric updates use `likelihood` or `0 < likelihood_ratio < 1`. It does not delete/disqualify the target; decisive contradictions become very high truth cost / near-zero belief.
- `prompts` — non-evidential provenance; source node motivates a test, assumption, branch, or follow-up node without changing belief by itself
- `leads_to` — premise/dependency used to derive the target; incoming `leads_to` edges form the target's base belief and are treated as independent unless covered by `factors` or legacy `premise_groups`
- `answers` — candidate solution satisfies a goal; must be `candidate_solution -> goal`

For multi-premise derivations, a `derived` node may have multiple incoming `leads_to` edges. Treat plain incoming premises as jointly required and independent for that conclusion. Use `supports`/`contradicts` for evidence that updates belief in an existing target, and `requires` for constraints or external dependencies the derived/candidate must satisfy.

Use top-level `factors` when two or more incoming numeric relation inputs for the same target are non-independent, such as shared source, duplicate evidence, logical overlap, or common latent cause. Factors are virtual relation records, not graph nodes: they cannot be frontier items, claims, candidates, or proof steps. Factor presence means non-independent; do not create factors for independent inputs.

For `leads_to`, the factor aggregation is `joint_probability`: it replaces the independent product for grouped premises while ungrouped incoming premises still contribute independently. For `supports`/`contradicts`, the factor aggregation is conditional `likelihood`: it replaces the product of grouped member likelihood updates while ungrouped likelihood edges still multiply normally. Do not set direct factor `likelihood_ratio`; use `if_target_true` and `if_target_false`.

```json
{
  "factors": [
    {
      "id": "F1",
      "relation": "leads_to",
      "target": "D1",
      "inputs": ["A1", "B1"],
      "aggregation": {"kind": "joint_probability", "probability": 0.72},
      "reason": "A1 and B1 share the same source, so they are not independent."
    },
    {
      "id": "F2",
      "relation": "supports",
      "target": "H1",
      "inputs": ["E1", "E2"],
      "aggregation": {"kind": "likelihood", "if_target_true": 0.54, "if_target_false": 0.18},
      "reason": "E1 and E2 are correlated observations."
    }
  ]
}
```

Legacy `premise_groups` remain accepted as shorthand for `leads_to` factors with `joint_probability`; prefer `factors` for new graphs.

Relationships are source of truth. Avoid manual `status` fields when they duplicate graph-derived view state such as winning/rank/dimmed/viable/rejected. In this schema, `status` is reserved for `test` nodes only.

Test node statuses:

- `proposed` — recommended next verification; not yet evidence and should not be treated as support. Renderers should visually distinguish it from evidence, e.g. shorter `proposed` label, different color, and dashed/dotted `prompts` edge.
- `performed` — check was conducted; add resulting `evidence`/`derived` nodes and connect them to affected branches
- `inconclusive` — performed but did not settle the claim

When a proposed test is later conducted, resume by updating the test node status to `performed` or `inconclusive`, adding the result as a new evidence/derived node when there is a result, then recomputing and re-sorting active frontier items against the latest graph evidence. `evidence_version` may be kept as trace metadata, but active dedupe always uses latest evidence and does not include `evidence_version`. Score changes alone do not reopen exhausted work. If evidence creates new work for an already-visited node, add a new frontier item for that node; if it only changes ranking/penalty, close the expansion with `no_new_work_reason`. Use `exhaustion_reason` only when marking a node or family `exhausted: true`. Keep the original proposed test node so the audit trail shows the recommendation-to-result transition.

Canonical pattern: `test` node = procedure; result `evidence` node = observed output. Example: `A1 --prompts--> T1`, `T1 --leads_to--> E9`, `E9 --contradicts--> A1`. Put `confidence` on the result evidence when scripts, OCR, external services, or manual transcription could be wrong.

## Hypothetical Branches

A hypothetical branch is an established reasoning chain under one or more assumptions. It represents one possible route to truth if the assumptions hold.

Rules:

- Treat derived nodes inside a hypothetical branch as conditional truth, not global truth.
- Every derived node under an assumption inherits dependency on that assumption until verified or proven independent.
- Do not create separate `solution` nodes. A final answer is the currently best-supported `candidate_solution`, derived from evidence, constraints, and search cost.
- Use `candidate_solution -> goal` with `answers` when the candidate satisfies the goal.
- Do not make “not solved”, “cannot establish”, or “missing dependency” a `candidate_solution` for a normal solve goal. That is a stop outcome or derived blocker, not an answer.
- A true “no valid solution exists” candidate is allowed only when it answers an accepted epistemic/negative goal and is supported by positive impossibility evidence.
- A method/source branch is not a `candidate_solution` unless it itself answers the goal; keep it as `assumption` or `derived`.
- Do not point an `assumption` directly at a `goal`; validation rejects this. Route it through tests, derived conclusions, or candidate answers. Direct `assumption -> goal` usually smuggles “this branch solves the task” without evidence.

### Multiple Goals

Use multiple `goal` nodes when the user explicitly accepts more than one outcome, such as solving the puzzle, proving no valid solution exists, or deciding evidence is insufficient under constraints.

Optional top-level goal policy:

```json
{
  "goal_policy": {
    "accepted_goals": ["G1", "G2"],
    "preferred_goals": ["G1"]
  },
  "goal_groups": [
    {"id": "GG1", "goals": ["G1", "G2", "G3"], "exclusive": true}
  ]
}
```

Rules:

- If `accepted_goals` is absent, all goal nodes are acceptable destinations.
- `preferred_goals` affects presentation/priority discussion, not validity.
- `exclusive: true` means goals in that group are mutually incompatible outcomes; do not add noisy candidate-to-other-goal `contradicts` edges.
- Candidate viability is per accepted goal: `candidate_solution -> accepted goal` with `answers`.
- Goal-group exclusivity is logical incompatibility between outcomes; contradictions apply through general truth-cost penalties.

For a normal solve request, use one goal. For “solve it or prove impossible”, use two accepted goals. For “solve it or say evidence is insufficient”, add an explicit epistemic goal; then “insufficient evidence” may be a candidate only for that goal.

## Report Metadata

Use optional `report` metadata when graph/presentation mode needs a readable human report. This is presentation metadata only; source of truth remains `nodes`, `edges`, `frontier`, and optional `events`.

Recommended shape:

```json
"report": {
  "candidates": [
    {
      "id": "CS1",
      "name": "Candidate label",
      "belief": 0.45,
      "truth_cost": 0.798508,
      "search_cost": 2.24,
      "weight": 0.72,
      "path_nodes": ["E1", "D2", "CS1"],
      "why": "Explains the most evidence with lowest constraint tension",
      "next_test": "Run the decisive verification"
    }
  ],
  "winning_path": ["Evidence A", "Assumption B", "Derived C", "Candidate D"],
  "next_verification": "..."
}
```

Do not encode rank words such as `Best:`, `Second:`, `Third:`, `Weak:` in candidate `name` or node `text`. Frontier rank is derived by sorting items by `search_cost`; candidate belief ranking is derived from `truth_cost`/`belief`. The renderer can display ordinal rank. Avoid storing a `rank` field unless the ordering comes from an external criterion that is not derivable from cost/belief.

Do not put `status` on `candidate_solution` nodes. Candidate rank/viability is derived from belief/effective truth cost, search cost, goal `answers` edges, and `answer_kind`. If the candidate table needs labels such as viable or contradicted, express them in `why`, `next_test`, likelihood edges, or graph relationships, not node `status`.

Candidate `answer_kind` schema:

```txt
exact_answer       exact answer to the accepted goal, e.g. plaintext/value/name
exact_method       exact reproducible method that entails the accepted goal
method_hypothesis  plausible method branch, not enough to answer a concrete solve goal
clue_path          clue-family/path candidate for an explicit clue-finding goal
blocker            insufficiency/blocker candidate for an explicit epistemic goal
```

For concrete solve/exact-answer goals, only `exact_answer` and `exact_method` may connect to the accepted goal. `method_hypothesis`, `clue_path`, and `blocker` must target explicit method/clue/epistemic goals or remain assumptions/derived nodes. Strict states (`stop_policy.severity: "error"`) require `answer_kind` on every `candidate_solution`.

Optional `path_nodes` on a candidate lists the main node IDs that should be highlighted when a report viewer focuses that candidate. Renderers may also include upstream support evidence/constraints for positive path nodes so entry evidence remains visible. Contradicting evidence/test nodes may be highlighted when explicitly listed, but should not automatically pull in their own upstream evidence unless the UI has a separate “why rejected” mode. If omitted, viewers should conservatively focus the candidate node and directly connected support where possible.

Do not present computed weights as calibrated posterior probabilities. If useful, compute:

```txt
belief = exp(-effective_truth_cost)
weight = belief / sum(belief of displayed candidates)
```

Label `weight` as relative among displayed candidates, not a calibrated real-world probability. Use `posterior` only when explicit evidence/test updates a prior/confidence and the uncertainty remains clearly labeled.

Use optional `presentation` metadata for curated graph/report views. Baseline HTML uses the fixed graph heading “Best explanation graph”. `presentation.title` may still describe the story for custom renderers, but should not replace the default graph heading.

```json
"presentation": {
  "include_nodes": ["E1", "E2", "A1", "CS1"],
  "highlight_nodes": ["E1", "A1", "CS1"],
  "dim_nodes": ["CS2", "CS3"],
  "title": "Why candidate 1 wins",
  "layout_hint": "evidence-left-candidates-right"
}
```

Presentation views may omit low-value nodes for readability. They must not introduce claims absent from the reasoning state.
