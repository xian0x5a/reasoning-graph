---
status: accepted
---

# The graph is memory and a stop gate, not a work queue

## Context

The skill drove reasoning as best-first search. Hypotheses and tests became frontier items with a search cost, the agent popped the cheapest one with `next --pop`, expanded it with `expand`, and `audit` checked that the pop order was best-first. Strict stops also required a minimum number of viable candidates or an empty frontier.

The countdown-island scenario compared a no-skill arm against the skill on the same problem:

| run set | arm | core | rubric pass | excellent | competitors | overclaims | mean wall | mean cost |
|---|---|---|---|---|---|---|---|---|
| Muse Spark 1.3, problem v1, queue skill, n=4 | no-skill | 4/4 | 28/28 | 15/20 | 20/20 | 8 | 4m15 | $0.013 |
| | reasoning-graph | 4/4 | 25/28 | 9/20 | 15/20 | 12 | 6m20 | $0.022 |
| DeepSeek V4.1 Flash, problem v4, record skill, n=3 | no-skill | 3/3 | 18/21 | 10/15 | 15/15 | 17 | 5m57 | $0.039 |
| | reasoning-graph | 3/3 | 19/21 | 7/15 | 11/15 | 12 | 12m56 | $0.099 |

With the queue, the skill matched no-skill only on core correctness, scored below it on every other quality column, and cost more. Every run's frontier peak came from rivals seeded at the root to satisfy the candidate gate, not from branching during search. The agents did the queue's bookkeeping instead of the problem's reasoning.

After the queue was taken out of the skill workflow (`record` in place of `seed`/`next`/`expand`, no rival gate), the skill matched no-skill on correctness, overclaimed less (12 vs 17), and never quoted belief numbers as calibrated posteriors (0/3 runs vs 2/3). It still covered fewer rival explanations and cost about 2.5 times as much.

The samples are small: one scenario, n=3 or n=4 per arm, one scorer per run. The DeepSeek runs used skill commit 1b12e6f, before the reviewer became required. They show direction, not effect sizes.

## Decision

The graph has three jobs: working memory the agent reads back, a gate on the final answer, and a live HTML view for a human. It does not choose the agent's next step.

- `record` appends progress with a reason and refreshes `<state>.html`. The agent works however it judges best and is told, not forced, to record as it goes.
- Observations cite a `source` and, for text, a verbatim `quote` that keeps the source's hedges. Any node may carry a `note` as the agent's own memory.
- A `solved` or `candidate_threshold_met` stop needs every accepted goal answered, a grounded best candidate at or above `belief_threshold`, a result for every test, and a passing review with no `record` after it. The review comes from an independent subagent that checks observations against their sources and the answer against the graph. ([ADR 0011](0011-the-record-is-memory-before-it-is-a-gate.md) amends this: the threshold, the review and `candidate_threshold_met` are removed.)
- Alternatives are the agent's call. `min_viable_candidates` remains only as an opt-in for when the user asks for alternatives.

The queue is removed from the CLI with no compatibility path: the `seed`, `next`, `assign`, `expand`, `frontier`, `sort`, `path`, standalone `rank`, and `costs` commands; `frontier`, `search_policy`, and `view.frontier` in state; the `init`, `seed`, `pop`, `assign`, `expand`, and `supersede` events; the `frontier_exhausted` outcome; search-cost ranking; and the audit's best-first replay. A read-only `beliefs` command prints computed beliefs. ([ADR 0010](0010-computed-belief-is-for-the-reader.md) removes it.)

## Consequences

- The belief contract (ADR 0003, ADR 0004) and node types (ADR 0005) are unchanged. Their mentions of frontier ranking are historical.
- `audit` checks record, review, rank, and stop events. It can no longer claim the agent followed a search order. It never could prove hidden cognition anyway.
- The final answer's trustworthiness rests on the stop gates and the reviewer, not on trace shape.
- State files with `frontier` or `search_policy` fail schema validation. Benchmark states under `test-results/` stay as evidence and are not migrated.
- Open: skill answers covered fewer rivals than no-skill. If rival coverage matters for a task, that belongs in the task's ask (`min_viable_candidates`) or the reviewer's checks, not in a default gate.
