# CLI without the stop certificate

Tracks issue #38. Decisions are recorded in the #38 comment of 2026-09-28.

## Goal

Cut the tool calls an agent spends on the CLI itself, so the graph costs less per round and later benchmarks do not pay for friction.

## Intention

In the resume loop of #37 the graph arm passed as many items as a notes file but cost 1.8 times as much. Most of the friction guarded the `solved` certificate of the old accuracy gate: the stop event, the lock behind it, the verified trace. #37 dropped that gate, so the guards go too. What stays is what protects the record for a reader: a well-formed graph, verbatim quotes, and the checks on a claimed answer.

## Scope & Constraints

In scope: the ten decisions under Decisions, the docs and ADRs that describe them, and one rerun of the graph arm.

Out of scope, each a later plan:

- The presentation eval and any change to how the HTML lays out the graph (#39). This plan adds one status line to the HTML and nothing else.
- A task too large for one note.
- Subagents handing patch files to the main agent.

Constraints:

- Breaking change to the state, the patch and the commands. No compatibility path; old fixtures are rewritten or removed. Old benchmark states under `test-results/` stay as evidence and are not migrated.
- Tests first for each behaviour below, seen failing for the expected reason.
- True Detective data is licensed for academic research only. Case texts, rubrics and outputs stay out of git.
- The rerun costs about $12 (the graph arm of `s55-loop-r1` cost $12.25).

## Work Plan

### 1. Count calls per command

Extend `tests/scenarios/exact-answer/loop_usage.py` to print tool calls per kind for round 1 and for later rounds: each `reasoning-graph` command, reads and writes of the kept files, the skill load, other shell calls. Run it on `s55-loop-r1` to fix the baseline the rerun is compared with.

### 2. `audit` replaces `stop`, `validate` and `doctor`

- `audit <state> [--draft <file>]` is read-only. It checks the graph, every quote, and the claim in the state.
- The claim is `summary.outcome` and `summary.answer`. A patch sets them with the top-level keys `outcome` and `answer`.

  | Outcome in the state | `audit` checks | Exit code |
  |---|---|---|
  | none | graph, quotes; lists what a `solved` claim still needs | 0 |
  | `solved` | the above, plus: every accepted goal is answered, the answer and the draft name one candidate per goal, that candidate rests on observations, every test has a result or `not_run` | non-zero if any fails |
  | `inconclusive`, `blocked` | graph, quotes | 0 |

- The first output line is the status: `in progress`, `solved: checks pass`, `solved: <n> checks fail`, or the other outcome by name.
- Removed: the commands `stop`, `validate`, `doctor`; the stop event; the refusal of writes after a stop.
- Removed with them: `stop_policy`, `init --strict`, `init --profile`, and the outcomes `budget_exhausted`, `candidate_count_met`, `user_stopped`. `init` takes `--goal` and `-o`.
- A failed check of a `solved` claim is always an error. There is no warning level.

### 3. The trace is removed

- The state holds no `events`. A state that carries them fails validation.
- A patch holds no `reason`. A patch that carries it is refused.
- `record` and `refresh` no longer compute a digest or log a hand edit. `refresh` still validates, rechecks every quote, and rewrites the HTML and the index.
- The index drops `Last record` and shows the outcome beside the answer.
- The list order of `nodes` and `edges` is the creation order: `record` appends and never reorders. One test and one sentence in `docs/driver.md` fix the rule.

### 4. An edge is identified by `from-to`

- Edges carry no `id` in a patch or in the state. An edge that carries one is refused.
- Groups, `update_edges` and `remove_edges` name an edge as `O1-H1`.
- Two new validation rules: one edge per ordered pair, and no hyphen in a node id.

### 5. `init` says what it created

`init` prints the id and text of the goal it created. `SKILL.md` names `G1` in the workflow.

### 6. One status line in the HTML

The HTML shows the status line of `audit`, computed when it renders. Nothing else in the view changes.

### 7. Docs and ADRs

- `skills/reasoning-graph/SKILL.md`, `docs/driver.md`, `docs/schema/*.md`, `README.md`, `docs/test-scenarios.md`.
- A new ADR: status is computed, not stored. It amends 0008, 0010 and 0011.
- Package version goes to 0.3.0.

### 8. Rerun the graph arm

Run id `s55-loop-r2`, the same 14 items, model and effort. Score with `score_loop.py`, count with `loop_usage.py`, post the result on #38.

## Validation

- Package checks pass: `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`.
- A smoke loop on one item finishes before the full rerun starts.
- In the rerun:
  - no write is refused because of a stop, which holds by construction
  - no hand edit of `state.json` strips or repairs anything the CLI wrote
  - no record fails on `G1`
  - passed items stay at 12 of 14, within run-to-run noise
  - tool calls and cost are reported against the notes file ($6.86, 115 calls)

## Progress

- [ ] 1. Calls per command
- [ ] 2. `audit` replaces `stop`, `validate`, `doctor`
- [ ] 3. Trace removed
- [ ] 4. Edge ids derived
- [ ] 5. `init` output
- [ ] 6. HTML status line
- [ ] 7. Docs and ADRs
- [ ] 8. Rerun and result on #38

## Surprises & Discoveries

Found while preparing the plan, from the transcripts of `s55-loop-r1`:

- **The duplicate-id failures were not a memory problem.** All 12 are `nodes id G1 already exists` in round 1. `init` creates the goal and prints nothing, and the first patch adds it again. 9 cost one extra call, 3 cost three.
- **The 1.3 times target of #38 is probably out of reach by removing friction alone.** A round of the notes-file arm takes 2.1 tool calls. A round of the graph arm takes 5.7 in round 1 and 4.6 later. One of them loads the skill, and at least two are `record` and the final check. Agents already chain the final checks: 41 of the 42 calls that ran `stop` also ran `validate` and `audit`, and 28 of them ran `record` too. So folding the three checks into one saves output tokens more than calls.
- **`refresh` ran 14 times**, 8 of them in round 1. Step 1 shows why.

## Decisions

1. `stop` becomes a read-only `audit`. A status computed on demand cannot go stale.
2. `validate` and `doctor` fold into `audit`.
3. The outcome and the answer are fields set by the patch, and they decide what `audit` checks.
4. The trace is removed, the patch `reason` with it. Notes about a node go on the node; anything else goes in a file of the agent's own.
5. Ids stay free-form. A counter-based id was dropped.
6. Creation order is the list order. A `step` field and a timestamp were dropped: nothing reads them today.
7. An edge is identified by `from-to`. Checked on 61 states: no pair is used twice and no node id has a hyphen.
8. `init` says what it created. An error naming the next free id was dropped: it would have offered `G2`.

9. `stop_policy` is removed whole: `severity`, `min_viable_candidates`, and with them `init --strict` and `init --profile`. They configured the stop gate, and there is no stop gate. A state that carries `stop_policy` fails validation.
10. The outcomes are `solved`, `inconclusive` and `blocked`. `budget_exhausted`, `candidate_count_met` and `user_stopped` are removed: the skill imposes no budget and counts no candidates. They came from the work queue that ADR 0006 removed.

`goal_policy` stays. It says which goals need an answer, which the checks of a `solved` claim read.

## Outcomes & Retrospective

Not started.
