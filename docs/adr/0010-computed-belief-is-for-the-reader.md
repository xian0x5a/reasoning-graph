---
status: accepted
supersedes: 0007-state-stores-computed-belief.md
amends: 0008-one-patch-carries-every-graph-edit.md
---

# Computed belief is for the reader, not the agent

## Context

ADR 0007 stored the computed `belief` on every claim so the agent could read it back, and a `belief_threshold` gated the stop. In #34 and #36 this steered the agent the wrong way:

- Belief did not track correctness (AUC 0.41 and 0.55), so a gate on it filtered nothing.
- Agents tuned scores until the threshold passed: 0.64 tuning records per run.
- A `posterior` field let the author overrule the graph's own evidence.

The number is still useful to a person. In a large graph it shows why one answer was preferred, and a weight that looks wrong is where a reader starts checking.

## Decision

- The state holds no computed belief. `record` and `refresh` do not write it, and a state or patch that carries `belief` fails validation.
- `belief_threshold` and `posterior` are removed.
- The `beliefs` command and the `rank` event are removed. `stop`, `audit` and `doctor` print no belief and no ranking.
- The renders compute belief when they run: `html`, `mermaid`, and the live `<state>.html`.
- The HTML marks an answer that is not the top-ranked candidate. The agent gets no warning.
- `stop` checks that the answer names a candidate that answers the goal, any candidate. The grounding gate applies to the named candidate.
- A goal's only candidate is its answer. Among several, the answer names exactly one; `stop --answer` sets it, so it costs no hand edit. ([ADR 0012](0012-status-is-computed-not-stored.md) moved these checks to `audit`, made the patch key `answer` the way to set the answer, and requires the answer to be named even for a goal's only candidate.)

## Consequences

- No gate depends on a number the agent can tune.
- A state file is smaller and cannot hold a stale belief, so the checks of ADR 0007 and the belief rewrite of ADR 0008 are gone.
- The agent can still run a render and read the numbers. Nothing asks it to.
- A wrong answer that outranks the right one is caught only by a reader.
