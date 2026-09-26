# Reasoning Graph CLI Reference

State shape, commands, events, audit checks, and semantic stop review. The workflow and the record patch live in `../SKILL.md`.

## Commands

Mutating commands rewrite the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout. Bookkeeping that records no new reasoning (fixing a typo, adding an obvious `source`, formatting JSON) can be edited directly.

```bash
reasoning-graph init --goal "Diagnose outage" --strict -o state.json
reasoning-graph record state.json --patch step.json   # append progress with a reason; refreshes state.html
reasoning-graph review state.json --reviewer <id> --verdict pass|fail --findings "<text>"   # reviewer's verdict
reasoning-graph beliefs state.json                 # computed belief per claim (--json for rows)
reasoning-graph doctor state.json                  # validate, compute beliefs, audit once stopped
reasoning-graph validate state.json                # schema/reference/belief sanity checks
reasoning-graph stop state.json --reason "CS1 is grounded above threshold and review passed" --outcome solved -o state.stopped.json
reasoning-graph validate state.stopped.json
reasoning-graph audit state.stopped.json           # event trace and stop gates
reasoning-graph stop-review state.stopped.json --draft answer.md  # final stop checklist
reasoning-graph mermaid state.json                 # emit Mermaid source
reasoning-graph html state.json -o graph.html      # render a report; record already keeps state.html current
reasoning-graph schema state                       # packaged JSON Schema (also: schema patch)
```

Use the installed `reasoning-graph` CLI. In a repository checkout, developers may run `uv --project packages/reasoning-graph run reasoning-graph ...`.

## State

```json
{
  "summary": {"title": "Reasoning Graph", "answer": "Compact answer shown above the graph."},
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Solve the problem"},
    {"id": "O1", "type": "observation", "text": "Observed failure", "source": "incident.log line 12", "quote": "request failed: token expired", "prior": 0.95},
    {"id": "C1", "type": "constraint", "text": "Must preserve API", "source": "user prompt"},
    {"id": "H1", "type": "hypothesis", "text": "Token clock skew", "note": "Check the NTP log before trusting this."},
    {"id": "CS1", "type": "candidate_solution", "text": "Resync the token server clock", "answer_kind": "exact_answer"}
  ],
  "edges": [
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "leads_to", "reasoning": "An expired token right after issue points to skew."},
    {"id": "H1-CS1", "from": "H1", "to": "CS1", "type": "leads_to", "reasoning": "The fix follows from the cause."},
    {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "This candidate supplies the requested answer."}
  ],
  "stop_policy": {"belief_threshold": 0.8, "require_review": true, "severity": "error"},
  "events": [
    {"step": 1, "action": "record", "reason": "Read the incident log", "add_nodes": ["O1", "H1", "CS1"], "add_edges": ["O1-H1", "H1-CS1", "CS1-G1"], "update_factors": []},
    {"step": 2, "action": "review", "reviewer": "reviewer-1", "verdict": "pass", "findings": "O1 matches its quote; the answer adds nothing the graph lacks."},
    {"step": 3, "action": "rank", "best": "CS1", "belief": 0.9025, "candidates": [{"node": "CS1", "belief": 0.9025, "effective_truth_cost": 0.102587}]},
    {"step": 4, "action": "stop", "reason": "CS1 is grounded above threshold and review passed", "outcome": "solved"}
  ]
}
```

Optional sections: `factors` (`docs/schema/factors.md`), `goal_policy` / `goal_groups` (`docs/schema/goals.md`), `report` / `presentation` / `view` (`docs/schema/reporting.md`).

`stop_policy` fields:

- `belief_threshold` — a `solved` or `candidate_threshold_met` stop needs a grounded best candidate at or above it
- `require_review` — such a stop also needs the latest review to pass with no `record` after it
- `min_viable_candidates` — opt-in, for when the user asks for alternatives: a candidate-bearing stop needs this many viable candidates. `init --strict` never sets it
- `severity` — `error` makes `audit` fail on stop-policy violations; `warning` reports them

## Record patch

`record` applies `reason` plus any of `nodes`, `update_nodes`, `edges`, `factors`:

- `nodes` is insert-only; duplicate ids are rejected.
- `update_nodes` replaces top-level fields on existing nodes, e.g. `{"id": "H1", "set": {"posterior": 0.72}}`; `id` and `type` are immutable. Use it to keep one node per claim as evidence arrives.
- `factors` adds or replaces factors by id.

The patch is applied atomically: if the merged graph fails validation (missing belief source, bad likelihood, dangling reference), nothing is written.

## Events

| action | written by | fields |
| --- | --- | --- |
| `record` | `record` | `reason`, `add_nodes`, `add_edges`, `update_factors`, and `updated_nodes` (ids with changed field names) when nodes were updated |
| `review` | `review` | `reviewer`, `verdict` (`pass`/`fail`), `findings` |
| `rank` | `stop`, for candidate-bearing outcomes | `best`, `belief`, `candidates` rows derived from the graph |
| `stop` | `stop` | `reason`, `outcome` |

Stop outcomes: `solved`, `candidate_threshold_met`, `candidate_count_met`, `budget_exhausted`, `blocked`, `user_stopped`, `inconclusive`.

`stop` checks every gate before writing anything:

- candidate-bearing outcomes (`solved`, `candidate_threshold_met`, `candidate_count_met`) need every accepted, non-optional goal answered (`docs/schema/goals.md`) and any `min_viable_candidates`
- `solved` and `candidate_threshold_met` also need the confidence gates in `../SKILL.md`: grounded best candidate, `belief_threshold`, test results, passing review

A failed gate names what is missing. Non-candidate outcomes only write the stop event. Nothing may be appended after `stop`.

## Audit

`audit` validates the state, then checks the trace:

- steps strictly increase; actions are `record`, `review`, `rank`, `stop`; the trace ends with exactly one `stop`
- each record has a reason and names nodes/edges/factors that exist; no node or edge is claimed as added by two events
- each review names a reviewer, a verdict, and findings
- `rank.best`, `rank.belief`, and `rank.candidates` rows match the values derived from the graph
- the stop outcome meets the gates above; under `severity: error` a violation fails the audit

`audit` and `doctor` print `events`, `records`, `reviews`, and `rankings` counts.

## Semantic Stop Review

`stop-review` runs after `stop` on the stopped state and prints:

```yaml
verdict: pass | fail
required_fixes: []
semantic_tricks_checked: []
notes: []
```

It fails when validation or audit fails, when the stop event lacks an outcome, when a candidate-bearing stop has no viable candidate or leaves an accepted goal open, or when `summary.answer`, `report.answer`, or the `--draft` file does not name the best candidate of each accepted goal by id or exact text. `--strict-warnings` promotes validation/audit warnings to required fixes.

Stop reasons state the real stopping condition: threshold met with review passed, requested candidate count met, budget exhausted, or blocker reached. "Best candidate has highest belief" is a tautology; ranking already guarantees it.

The reviewer subagent that gates the stop (`../SKILL.md` Review) checks what the CLI cannot:

- each observation the answer relies on says no more than its `quote` and `source`
- every factual claim in the answer traces to an observation
- evidence in the sources that cuts against the answer is recorded and addressed
- blockers are not disguised as answer candidates for normal solve goals
- contradictions penalize only the branches they bear on
