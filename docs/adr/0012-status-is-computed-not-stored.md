---
status: accepted
amends:
  - 0008-one-patch-carries-every-graph-edit.md
  - 0010-computed-belief-is-for-the-reader.md
  - 0011-the-record-is-memory-before-it-is-a-gate.md
---

# The status of the answer is computed, not stored

## Context

`stop` wrote a certificate into the state: a stop event with an outcome. Everything after it was refused, and `audit` verified the event trace behind it. That guarded the `solved` stop of an accuracy gate, which ADR 0011 dropped.

The resume loop (Sonnet 5.5, 14 True Detective items) is the case the certificate did not plan for: the answer is rejected and the agent has to keep working.

- The graph arm passed as many items as a plain notes file, 12 of 14, at 1.8 times the cost: 246 tool calls against 115.
- 13 of 14 loops hit the lock: 38 refused writes, 23 hand edits of the state, most of them to strip the stop event.
- `validate`, `audit`, `doctor` and `stop` each repeated the checks of the one before. 41 of the 42 calls that ran `stop` also ran `validate` and `audit`.
- The trace was 16% of the state file. Its readers were `audit` and one line of the index.
- 225 of 245 edge ids were exactly `from-to`: the agent wrote the same thing twice.
- All 12 duplicate-id failures were a first patch adding `G1` again. `init` had created it and printed nothing.

## Decision

- `audit` is the one check, and it is read-only. It checks the graph and every quote, and the answer checks once an answer is claimed. `stop`, `validate` and `doctor` are removed.
- The claim is `summary.answer`. A patch sets it with `answer`, and an empty string withdraws it.

  | State | `audit` checks | Exit code |
  |---|---|---|
  | `answer` is empty | graph, quotes; lists what an answer would still need | non-zero if one fails |
  | `answer` is set | the above, plus the answer checks | non-zero if one fails |

- The answer is always named. A goal's only candidate is not its answer, or a half-finished graph with one candidate would count as a claim.
- The first line `audit` prints is the status: `no answer claimed`, `answer CS1: checks pass`, or `answer CS1: 2 checks fail`. The HTML view shows the same line, computed when it renders.
- There is no outcome. `inconclusive` and `blocked` changed no check; the reason for giving up is a hypothesis node and a line in the final response. `budget_exhausted`, `candidate_count_met` and `user_stopped` came from the work queue that ADR 0006 removed.
- `stop_policy` is removed whole, with `init --strict` and `init --profile`. A failed answer check is always an error.
- The state holds no `events` and a patch holds no `reason`. `record` and `refresh` compute no digest and log no hand edit; they check the whole graph and every quote on each call. Notes about a node go on the node.
- The list order of `nodes` and `edges` is the creation order: `record` appends and never reorders. A `step` counter and a timestamp were considered and dropped, because nothing reads them.
- An edge is identified by its ends, written `from-to`, and carries no `id`. One edge per ordered pair, and no hyphen in a node id. Node ids stay free-form; a counter-based id was considered and dropped.
- `init` prints the goal it created.
- Removed fields and commands are rejected with a message that names what replaced them, not converted.

## Consequences

- Nothing locks the state. After a rejected answer, one patch records what the user said, links it to the rejected candidate, and withdraws the claim.
- A status cannot go stale, because no status is stored.
- The file alone does not tell "gave up" from "still working". Both are a state with no claimed answer.
- A hand edit is checked by the next `record`, `refresh` or `audit`, and leaves no mark. The digest made casual tampering visible; nothing does now.
- The state cannot say which record added a node, or what a checkpoint was for, beyond the list order and the notes.
- Two parallel edges between the same pair cannot be written. A `supports` and a `contradicts` from one source to one target have to be weighed into one edge.
- Old states fail validation. Benchmark states under `test-results/` stay as evidence and are not migrated.
