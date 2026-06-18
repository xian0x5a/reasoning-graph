# Reasoning Graph Exploration Guide

Input ledger extraction, branching/candidate hygiene, stopping rules, and final quality checks.

## Input Ledger Extraction

User input often arrives as an unstructured block, not labeled evidence/constraints. Before branching, classify the provided input into a small ledger. This extraction step labels known inputs; acquiring missing evidence belongs to the exploration workflow.

Workflow:

1. Extract the `goal` from explicit request wording. If multiple goals conflict, ask or state the chosen primary goal.
2. Build the initial ledger from observed/source-backed inputs and requirements using the canonical node types in `schema.md`.
3. Keep plausible interpretations as initial assumptions/frontier branches, not evidence.
4. If a constraint is inferred from intent rather than explicit, mark it as inferred in the text or `source`; ask the user if it is high-impact or ambiguous.
5. Record source metadata on evidence/constraint nodes when useful:

```yaml
- id: E3
  type: evidence
  text: "Production logs show JWT signature verification failed"
  source: "user prompt"
  confidence: 0.95

- id: C2
  type: constraint
  text: "Avoid rotating all user sessions unless necessary"
  source: "explicit user requirement"
```

Keep the ledger concise. Merge tiny related evidence when that improves readability, but do not merge evidence that plays different logical roles in supporting or penalizing branches.

Graph-mode HTML must make evidence and constraint nodes readable with IDs and sources. A filterable node-detail list and node popup modals can satisfy this; do not duplicate a separate evidence/constraint ledger section when it makes the report longer without adding clarity.

## Exploration Algorithm

Evidence acquisition boundary: input extraction only classifies known inputs. Before initializing the frontier, a bounded context pass may add cheap, source-backed evidence such as files, logs, docs, or web sources when allowed. After search starts, non-trivial checks, searches, or experiments should be modeled as `test`/frontier work; append observed result evidence during expansion.

Use this workflow:

1. Frame the `goal`.
2. Build the initial ledger from prompt/context inputs and source metadata where useful.
3. If cheap missing evidence is needed before branching, do a bounded context pass and add observed results to the ledger with sources.
4. Try direct derivation if obvious; otherwise initialize frontier from plausible assumptions or unresolved claims.
5. For each assumption, assign `prior`, truth cost, and reason. For uncertain evidence/results, assign `confidence`. Prefer branching from generic/structural assumptions first, then specialize with derived nodes or candidate solutions. Assumptions should be atomic/testable premises, not whole-solution-shaped duplicates of candidate answers.
6. Pop the frontier item with lowest current `search_cost`. For complex reasoning, use `uv run rg next state.json --pop -i` before major search moves: substantial reasoning, branch selection, evidence-gathering tool use, searches, or tests. Bookkeeping that does not change the search does not need a pop.
7. Choose treatment for the popped focus. Expand it directly when structure is missing; record async observation-heavy work with `uv run rg assign state.json --item <id> -i`; rank/close it when no new work is needed. Assigned items become in-flight and no longer block `next --pop`; assigning additional async work is blocked at the configured concurrency limit.
8. Digest expansion/probe results. Ask: what does this imply, what sibling hypotheses split from here, what cheap tests discriminate them, what contradictions would penalize them, and what candidate answer becomes possible? Add multiple meaningful child branches when available. In discovery-style tasks, create `candidate_solution` nodes only after a branch has enough clue/evidence support to be answer-shaped; do not preload final candidates as unexplored buckets.
9. If a result arrives from direct expansion or async probe work, add it as evidence/derived evidence and add calibrated `supports`/`contradicts` likelihood edges or an explicit `posterior` update. Then add child frontier items and re-sort. Let best-first priority choose which child to explore next. Reopen only when evidence creates new work; score-only updates stay closed.
10. Continue until adaptive stopping conditions are met and no assigned probe needed for the stop remains in-flight.
11. Return compact answer or graph artifact depending on output mode.

Default stopping behavior must be metric-gated, not discretionary.

A normal stop is acceptable when at least one is true:

- event-reachable frontier is exhausted,
- enough viable candidates have been explored (`min_viable_candidates`, default target usually 3 for comparison tasks),
- strongest viable candidate belief crosses an explicit threshold (for example `belief_threshold: 0.8`),
- an explicit external budget is reached and the graph records the remaining live frontier items as unfinished, not exhausted.

Do not stop on an epistemic/unresolved blocker while meaningful answer-goal frontier items remain live unless the state has an explicit stop policy allowing that. This is lazy-stop territory: the graph must prove search got enough candidates, got enough confidence, or genuinely exhausted/blocked the live frontier.

Recommended strict policy for benchmark/search tasks:

```json
"stop_policy": {
  "min_viable_candidates": 3,
  "belief_threshold": 0.8,
  "max_live_frontier_items": 0,
  "require_frontier_exhausted_for_epistemic_stop": true,
  "severity": "error"
}
```

With this policy, stopping is allowed if there are no live frontier items, or at least 3 viable candidates, or a viable candidate has belief >= 0.8. Selecting an unresolved/epistemic candidate while live frontier remains is an audit failure.

Other stopping rules:

- when the user asks for competing explanations/candidates, list ranked candidates only for branches that were actually expanded, directly tested, or explicitly supplied by the user and clearly marked as not yet explored
- early stop is allowed when the best candidate crosses the belief threshold, but then do not pad the ranked candidate list with unexplored alternatives; mention them only as unexpanded possibilities if useful
- stop early when alternatives are trivial or directly contradicted only if their likelihood updates make them clearly dominated, and record the contradiction evidence/cost impact
- contradicted candidate solutions may remain viable goal-linked candidates, but their lowered belief should not satisfy a high-confidence target unless the stop policy threshold still passes
- ask user before deepening search if more exploration would cost meaningful time

A candidate solution is valid only if it:

- reaches the goal or gives an actionable answer
- satisfies known constraints
- has no unresolved contradiction
- lists remaining assumptions or uncertainty
- has a search/truth cost estimate when branch ranking matters

Assumption and candidate hygiene:

- Prefer generic structural branch assumptions before specific final answers, e.g. `single-root-cause model`, `multi-factor interaction model`, `missing-configuration model`, `dependency/version mismatch model`.
- Specific assumptions are allowed when they are atomic/testable, e.g. `the config file is loaded from the expected path`, `the dependency version changed after the last working run`, or `input can arrive before initialization completes`.
- Avoid assumptions that already bundle the answer, e.g. `package X broke because config Y stopped loading after deploy Z`. Split that into a generic branch assumption plus derived/support nodes and a candidate solution.
- Litmus: if the assumption already answers the goal, or contains several uncertain premises joined together, make it a candidate/derived chain instead.
- Candidate solutions are usually conclusions of explored branches, not initial buckets for every imaginable answer. Start with assumptions/tests, expand clue/evidence chains, then emit a `candidate_solution` when the branch becomes complete enough to answer the goal.
- Early candidate placeholders are valid only when the option is user-supplied, already obvious from strong direct evidence, or useful as a low-priority hypothesis to test later.
- If a candidate enters the frontier before supporting evidence is expanded, give it appropriately high truth/constraint-tension cost and mark why it is weak or provisional. A jump-to-answer candidate without evidence should not outrank evidence-backed branches.
- Keep early candidates unresolved/unranked until each option has been expanded or directly contradicted by evidence. Ranked report candidates should correspond to explored/penalized branches, not merely imagined options. Evidence-contradicted candidates remain visible endpoints with lower belief; they are useful audit evidence and can remain viable only if their effective truth cost still meets the stop policy.
- Expand coarse possibility families first, not micro-variants. For example, create one frontier item for `WebCrypto AES-GCM layout family`, not 500 items for PBKDF2 iteration counts. Concrete variants belong inside the popped family expansion/test.
- Authoritative clue heuristic: if an official hint, doc, maintainer comment, theorem condition, log message, test failure, or other high-authority clue appears, spawn interpretation branches before brute-force branches. Mark the clue-family node with `clue_family: true` and `salience` (for example `0.8`) when dropping it would materially change the search. Interpretations of the clue usually deserve lower `verification` and `reasoning_complexity` cost than broad search because they can sharply reduce the space. Do not let concrete but expensive brute force outrank cheap interpretation of an authoritative clue.
- Bounded-negative heuristic: a failed bounded test penalizes only the exact tested interpretation, not the parent clue family. If a high-prior clue branch fails one direct test, add live frontier siblings for refined interpretations or add a derived node explaining why the whole family is actually exhausted. Do not convert `one tested variant failed` into `strong clue path dead`. No special backtracking mode is needed; best-first search continues by popping the next live frontier item.
- Partial-expansion/revival heuristic: popping a family/clue item means one expansion attempt, not permanent exhaustion. On first pass, expand obvious sibling interpretations broadly enough to avoid single-variant tunnel vision. If later evidence or a failed child shows the family was under-expanded, revive it by adding a new child `assumption`/`test` node under the original family node and a frontier item pointing to that child. Re-queueing the same family node is allowed only as a temporary continuation when no specific child branch can yet be named.
- Continuation invariant: when prior reports/evaluations are allowed but prior graph state is not, reconstruct high-salience clue families from the reports as explicit graph nodes. Do not collapse a clue family into generic “prior probes failed” evidence. If the family is not fully exhausted, it must have either a live frontier continuation or an `exhausted: true` node with `exhaustion_reason`.
- Divergence floor: for high-salience clue/family expansion, aim to create at least three child frontier branches: one direct/literal interpretation, one structural/transform interpretation, and one low-prior wildcard. Branching does not mean you must spend time on every branch immediately: search-cost ordering keeps low-prior or expensive branches low in the queue until better paths are exhausted or contradicted. Therefore adding a plausible low-prior branch is cheap and encouraged; silently omitting it is more dangerous than carrying it in the frontier. This is a soft floor by default, not a command to invent fake branches. If fewer branches are meaningful, record `under_branching_reason`, `existing_sibling_frontier`, or `exhausted: true` with `exhaustion_reason`. Audit defers branch-factor warnings until the stop reason claims exhaustion/completion, unless `branch_policy.enforce_on` is `always` or `severity` is `error`.
- A one-child expansion is a soft signal to reconsider whether meaningful sibling branches were missed. The goal is to reveal possible solution paths, not to make one chosen path look reasonable after the fact.

## Quality Checks

Before final answer, check:

- Is the goal explicit?
- Is evidence separated from constraints?
- Are assumptions scoped and assigned priors?
- Does every viable candidate solution answer the goal instead of merely naming a method/source branch?
- When a high-prior clue branch got a bounded negative result, did the graph refine sibling interpretations instead of treating the entire clue family as dead?
- If a family/clue node was only partially expanded, did the graph add child branch frontier items or explicitly justify family exhaustion?
- Did constraints add explicit cost/blocking evidence for invalid branches?
- Did search keep meaningful alternatives instead of stopping at first plausible answer?
- When an authoritative clue appeared, did the graph spawn and prioritize interpretation branches before brute-force or implementation-guessing branches?
- Are priors/costs shown only when useful?
- Is uncertainty labeled instead of hidden?
- For complex reasoning, was the state built or updated through the driver loop before major search moves, while trivial bookkeeping stayed lightweight?
- After `uv run rg stop` produced a stopped candidate state, did semantic stop review pass before the stopped state was promoted?
- If driver events exist, did `uv run rg audit` finish without unexplained warnings, especially unexpanded `candidate_solution` nodes?
- In graph mode, was the requested HTML artifact generated by `uv run rg html` from the validated state, not hand-written from scratch?
- Can the user open the HTML artifact and see summary + candidate table + evidence/constraint node details with sources?
- Is there a curated presentation graph, not only the full audit graph?
- If the full graph is dense, is it navigable with pan/zoom instead of tiny unreadable SVG?
- Do graph nodes open popup/modal detail cards without forcing the user away from the canvas?
