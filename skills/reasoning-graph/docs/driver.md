# Reasoning Graph CLI Reference

State shape, commands, events, audit checks, and semantic stop review. The workflow and the record patch live in `../SKILL.md`.

## Commands

Mutating commands rewrite the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout. After a hand edit of the state, the next `record` or `stop` checks and logs it; `refresh` does the same without writing anything else.

```bash
reasoning-graph init --goal "Diagnose outage" --strict -o state.json
reasoning-graph record state.json --patch - <<'JSON'   # append progress with a reason; refreshes state.html
{"reason": "...", "nodes": [...], "edges": [...]}
JSON
reasoning-graph refresh state.json                 # take in a hand edit now: validate, recheck quotes, recompute beliefs, log it
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
    {"id": "O1", "type": "observation", "text": "Observed failure", "source": "incident.log line 12", "quote": "request failed: token expired", "prior": 0.95, "belief": 0.95},
    {"id": "C1", "type": "constraint", "text": "Must preserve API", "source": "user prompt"},
    {"id": "H1", "type": "hypothesis", "text": "Token clock skew", "note": "Check the NTP log before trusting this.", "belief": 0.95},
    {"id": "CS1", "type": "candidate_solution", "text": "Resync the token server clock", "answer_kind": "exact_answer", "belief": 0.95}
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
    {"step": 3, "action": "rank", "best": "CS1", "belief": 0.95, "candidates": [{"node": "CS1", "belief": 0.95, "effective_truth_cost": 0.051293}]},
    {"step": 4, "action": "stop", "reason": "CS1 is grounded above threshold and review passed", "outcome": "solved"}
  ]
}
```

Claims carry `belief`, written by the CLI after every `record`; it is never authored.

Optional sections: `factors` (`docs/schema/factors.md`), `goal_policy` / `goal_groups` (`docs/schema/goals.md`), `report` / `presentation` / `view` (`docs/schema/reporting.md`).

`stop_policy` fields:

- `belief_threshold` — a `solved` or `candidate_threshold_met` stop needs a grounded best candidate at or above it
- `require_review` — such a stop also needs the latest review to pass, on a graph whose digest matches the current one
- `min_viable_candidates` — opt-in, for when the user asks for alternatives: a candidate-bearing stop needs this many viable candidates. `init --strict` never sets it
- `severity` — `error` makes `audit` fail on stop-policy violations; `warning` reports them

## Record patch

`record` applies `reason` plus any of these operations, in this order: removals, then updates, then additions.

- `remove_nodes`, `remove_edges`, `remove_factors` take id lists; each id must exist. Removing a node also removes every edge touching it, and the event lists those edges. Factors are never removed implicitly: a factor left pointing at a removed node or edge fails validation, so remove or replace it in the same patch.
- `update_nodes` and `update_edges` take items `{"id": ..., "set": {...}, "unset": [...]}` with at least one of `set` or `unset`. `set` replaces top-level fields; `unset` deletes fields the item has. A node's `id` and `type` and an edge's `id`, `from`, and `to` are immutable. Use `update_nodes` to keep one node per claim as evidence arrives.
- `nodes` and `edges` are insert-only; an id that exists after the removals is rejected. An id removed earlier in the same patch may be added again.
- `factors` adds or replaces factors by id.
- `belief` is rejected in `nodes` and `update_nodes`; `record` rewrites every claim's `belief` from the merged graph.
- Every observation whose `source` starts with a local text file (resolved from the state file's directory) must quote it verbatim: each `...`-separated fragment of `quote` has to appear in the file. Line breaks, markdown markers, quote-mark style, and case are ignored. Other sources are not checked. `record` and `refresh` recheck every quote on each call, not only the patched ones.

The patch is applied atomically: if the merged graph fails validation (missing belief source, bad likelihood, dangling reference) or a quote check, nothing is written.

## Hand edits and the graph digest

`record`, `refresh`, `review`, and `stop` events store `graph_digest`: a short sha256 over nodes (without `belief`), edges, and factors, each sorted by id, plus `stop_policy`, `goal_policy`, and `goal_groups`. It is how the CLI notices an edit it did not make.

- A state whose digest differs from the latest `record` or `refresh` event was edited by hand. `refresh`, `record`, and `stop` take such an edit in: the graph must validate and every quote must match its source, and a `refresh` event is logged. `record` runs those checks on the patched graph, so a patch can repair a hand edit, and logs the `refresh` event just before its own.
- The `refresh` event lists as removals any object an earlier event added that the state no longer has, so `audit` stays consistent. Objects added by hand stay untraced, like the goal `init` writes.
- `refresh` also rewrites beliefs and `state.html`; with no hand edit it logs nothing.
- A review is stale when its digest differs from the current graph's.
- `stop` validates the graph and computes every belief itself before the gates; stored beliefs are overwritten, never read. The stop event's digest lets `audit` detect an edit made after `stop`.

## Events

| action | written by | fields |
| --- | --- | --- |
| `record` | `record` | `reason`, `add_nodes`, `add_edges`, `update_factors`; when non-empty, `updated_nodes` and `updated_edges` (ids with changed field names) and `remove_nodes`, `remove_edges`, `remove_factors` |
| `refresh` | `refresh`, `record`, or `stop`, after a hand edit | `remove_nodes`, `remove_edges`, `remove_factors` when non-empty |
| `review` | `review` | `reviewer`, `verdict` (`pass`/`fail`), `findings` |
| `rank` | `stop`, for candidate-bearing outcomes | `best`, `belief`, `candidates` rows derived from the graph |
| `stop` | `stop` | `reason`, `outcome` |

`record`, `refresh`, `review`, and `stop` events also carry `graph_digest`.

Stop outcomes: `solved`, `candidate_threshold_met`, `candidate_count_met`, `budget_exhausted`, `blocked`, `user_stopped`, `inconclusive`.

`stop` checks every gate before writing anything:

- candidate-bearing outcomes (`solved`, `candidate_threshold_met`, `candidate_count_met`) need every accepted, non-optional goal answered (`docs/schema/goals.md`) and any `min_viable_candidates`
- `solved` and `candidate_threshold_met` also need the confidence gates in `../SKILL.md`: grounded best candidate, `belief_threshold`, test results, passing review

A failed gate names what is missing. Non-candidate outcomes only write the stop event. Nothing may be appended after `stop`.

## Audit

`audit` validates the state, then checks the trace:

- `validate` fails on a stored `belief` that differs from the recomputed one
- steps strictly increase; actions are `record`, `refresh`, `review`, `rank`, `stop`; the trace ends with exactly one `stop`, whose `graph_digest` matches the final graph
- each record has a reason. Replaying `record` and `refresh` events in order (each one's removals, then its additions), no node or edge is added while the trace still holds it, and every object the trace still holds exists in the graph
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
