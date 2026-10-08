---
status: accepted
amends: 0006-graph-is-memory-and-stop-gate-not-a-work-queue.md
---

# The record is memory before it is a gate

## Context

ADR 0006 gave the graph three jobs: working memory, a gate on the final answer, and a live view. The skill vs no-skill A/B and its follow-up runs tested the gate as an accuracy tool (Sonnet 5, 22 True Detective items):

- Accuracy did not improve: 10 to 12 of 22 right, with or without the skill.
- The skill cost 6.3 times a run without it. The review loop was the largest part at $0.20 per run.
- A reviewer on the same model shared the agent's misreading of the sources.

What the skill does reliably is keep a record. This decision repositions it: a memory layer first, a presentation for a reader on top.

## Decision

- The reviewer is removed: the `review` and `stop-review` commands, `require_review`, the stale-review check and the `review` event. An agent that wants a second opinion records it as a `test` node like any other check.
- `stop` keeps the checks a machine can make: quotes are verbatim, every test has a result or is marked `not_run`, every accepted goal is answered, the answer names a candidate, and that candidate rests on observations. ([ADR 0012](0012-status-is-computed-not-stored.md) keeps the checks and removes `stop`: `audit` runs them read-only, and nothing locks the state.)
- `candidate_threshold_met` is removed as an outcome. Without a threshold it equals `solved`. ([ADR 0012](0012-status-is-computed-not-stored.md) removed every outcome.)
- `record` refreshes `<state>.index.md` beside the state: goals, then what is open, then one line per node and edge. It holds no quotes and no belief. It is what an agent reads first on resume.
- The main agent is the only writer. `record` rewrites the whole state, so two writers lose updates. Subagents read the index and return findings; a delegated check is a `test` node marked `not_run` until its result is in.
- When to record and how much stays the agent's call. No budget is enforced.

The rest of ADR 0006 holds: the graph does not choose the agent's next step.

## Consequences

- The final answer's trustworthiness rests on the mechanical checks and on a reader, not on a reviewer.
- Whether the graph is a better memory than a plain notes file is measured by the resume loop under `tests/scenarios/exact-answer/`.
- Open: subagents handing patch files to the main agent. Add it only if a measurement shows the main agent's writing is the bottleneck.
