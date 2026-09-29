# Reasoning Graph CLI Reference

State shape, the index file, commands, and audit checks. The workflow and the record patch live in `../SKILL.md`.

## Commands

`record` rewrites the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout. `audit`, `mermaid`, `html`, and `schema` write nothing to the state.

```bash
reasoning-graph init --goal "Diagnose outage" -o state.json   # creates goal G1 and says so
reasoning-graph record state.json --patch - <<'JSON'   # apply a patch; refreshes state.html and state.index.md
{"nodes": [...], "edges": [...], "answer": "CS1"}
JSON
reasoning-graph refresh state.json                 # after a hand edit: validate, recheck quotes, rewrite the views
reasoning-graph audit state.json                   # read-only: graph, quotes, and the claimed answer
reasoning-graph mermaid state.json                 # emit Mermaid source
reasoning-graph html state.json -o graph.html      # render a report; record already keeps state.html current
reasoning-graph schema state                       # packaged JSON Schema (also: schema patch)
```

Use the installed `reasoning-graph` CLI. In a repository checkout, developers may run `uv --project packages/reasoning-graph run reasoning-graph ...`.

## State

```json
{
  "summary": {"title": "Reasoning Graph", "answer": "CS1"},
  "nodes": [
    {"id": "G1", "type": "goal", "text": "Solve the problem"},
    {"id": "O1", "type": "observation", "text": "Observed failure", "source": "incident.log line 12", "quote": "request failed: token expired"},
    {"id": "C1", "type": "constraint", "text": "Must preserve API", "source": "user prompt"},
    {"id": "H1", "type": "hypothesis", "text": "Token clock skew", "note": "Check the NTP log before trusting this."},
    {"id": "CS1", "type": "candidate_solution", "text": "Resync the token server clock", "answer_kind": "exact_answer"}
  ],
  "edges": [
    {"from": "O1", "to": "H1", "type": "leads_to", "note": "An expired token right after issue points to skew."},
    {"from": "H1", "to": "CS1", "type": "leads_to"},
    {"from": "CS1", "to": "G1", "type": "answers"}
  ]
}
```

The state holds what you authored, nothing computed and no trace of how it got there:

- `summary.answer` is the claim `audit` checks. It is empty while no answer is claimed.
- The list order of `nodes` and `edges` is the order they were recorded in.
- Belief is computed when the graph is rendered (`cost-model.md`), and so is the status of the claim.

Optional sections: `factors` (`docs/schema/factors.md`), `goal_policy` / `goal_groups` (`docs/schema/goals.md`), `report` / `presentation` / `view` (`docs/schema/reporting.md`).

Removed, and rejected by validation: `events`, `stop_policy`, and an `id` on an edge.

## Edge identity

An edge carries no id. It is identified by its ends, written `from-to`: the edge from `O1` to `H1` is `O1-H1` in `update_edges`, `remove_edges`, and the `edges` of a group. Two rules keep that name unique:

- one edge per ordered pair; to change an edge, use `update_edges`
- no hyphen in a node id

## Index file

`record` and `refresh` write `<state>.index.md` beside the state (`state.json` gives `state.index.md`; `record -o next.json` gives `next.index.md`). It is the compact read view: reread it after a context reset, and hand it to a subagent, instead of the whole state.

```md
# Reasoning graph index
- G1 goal: Who did it?
Answer: CS1

## Open
- H2 hypothesis: The butler did it
- T2 test (no result): Ask the cook
- T3 test (not run: The case file has none): Compare dental records

## Nodes
- O2 observation (score 3): The gardener says he stayed late [problem.md]
- CS1 candidate_solution: The gardener

## Edges
- O1 -contradicts(5)-> H2 | note: Nine is before the theft
- H1 -leads_to-> CS1

## Groups
- F1 [O2-H1, O3-H1] score 4 | note: Both place him on site
```

- Goals come first, with the claimed answer.
- **Open** lists hypotheses that rest on no claim premise yet, tests without a result, and tests marked `not_run`.
- A line gives id, type, text, and the source ref in brackets. A score shows only where it departs from the default. Notes follow `| note:`.
- Within a section, lines keep the order of the state's lists.
- The index holds no quote and nothing computed. It is a view: edit the state through a patch, never the index.

## Record patch

`record` applies these operations, in this order: removals, then updates, then additions. A patch holds at least one field.

- `remove_nodes`, `remove_edges`, `remove_factors` take id lists; each id must exist. Removing a node also removes every edge touching it. Groups are never removed implicitly: a group left naming a removed edge fails validation, so remove or replace it in the same patch.
- `update_nodes` and `update_edges` take items `{"id": ..., "set": {...}, "unset": [...]}` with at least one of `set` or `unset`. `set` replaces top-level fields; `unset` deletes fields the item has. A node's `id` and `type` and an edge's `from` and `to` are immutable. Use `update_nodes` to keep one node per claim as evidence arrives.
- `nodes` and `edges` are insert-only; a node id or an edge that exists after the removals is rejected. One removed earlier in the same patch may be added again.
- The list order of `nodes` and `edges` is the order they were recorded in: `record` appends and never reorders, and nothing else records that order.
- `factors` adds or replaces correlation groups by id.
- `answer` sets `summary.answer`; an empty string withdraws the claim.
- `belief` is rejected in `nodes` and `update_nodes`. `reason` is rejected: the state keeps no log, so what is worth keeping goes in a `note`.
- Every observation whose `source` starts with a local text file (resolved from the state file's directory) must quote it verbatim: each `...`-separated fragment of `quote` has to appear in the file. Line breaks, markdown markers, quote-mark style, and case are ignored. Other sources are not checked. `record` and `refresh` recheck every quote on each call, not only the patched ones.

The patch is applied atomically: if the merged graph fails validation (a removed field, a score off the scale, a dangling reference) or a quote check, nothing is written. Quote and validation failures are reported together, so one run lists everything to fix.

## Hand edits

A hand edit is checked, not logged. `refresh` validates the graph, rechecks every quote, and rewrites `state.html` and `state.index.md`; it does not rewrite the state. `record` runs the same checks on the patched graph, so a patch can repair a hand edit.

## Audit

`audit <state>` reads the state and writes nothing. Its first output line is the status. Failed checks go to stderr as `error:` lines.

| State | Checks | Status line | Exit code |
| --- | --- | --- | --- |
| `summary.answer` is empty | graph, quotes | `no answer claimed` | non-zero if one fails |
| `summary.answer` is set | graph, quotes, answer checks | `answer CS1: checks pass`, `answer CS1: 1 check fails`, `answer CS1: 2 checks fail` | non-zero if one fails |

While no answer is claimed, `audit` lists what an answer would still need as `needs:` lines: unanswered goals and tests without a result. They do not fail the audit.

Answer checks:

- every accepted, non-optional goal is answered (`docs/schema/goals.md`)
- `summary.answer` names exactly one candidate for each of those goals, by id as a whole word or by exact text. A goal's only candidate is not its answer until it is named, and naming more than one is rejected
- `report.answer`, when set, names the same candidate
- the answer candidate is evidence-grounded, and every test has a result or `not_run` (`../SKILL.md`)

`report.answer` without `summary.answer` fails validation: the view would show an answer nothing checked.

The HTML view shows the same status line, computed when it renders.

Nothing is stored about how the work ended. "Inconclusive" or "blocked" is a state with no claimed answer, a hypothesis that records the blocker, and a final response that says so.

## What the CLI cannot check

The CLI checks the record, not the reasoning. It cannot tell whether:

- each observation the answer relies on says no more than its `quote` and `source`
- every factual claim in the answer traces to an observation
- evidence in the sources that cuts against the answer is recorded and addressed
- blockers are not disguised as answer candidates for normal solve goals
- contradictions penalize only the branches they bear on
