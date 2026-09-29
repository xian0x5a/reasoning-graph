# CLI without the stop certificate

Tracks issue #38. Decisions are recorded in the #38 comment of 2026-09-28.

## Goal

Cut the tool calls an agent spends on the CLI itself, so the graph costs less per round and later benchmarks do not pay for friction.

## Intention

In the resume loop of #37 the graph arm passed as many items as a notes file but cost 1.8 times as much. Most of the friction guarded the `solved` certificate of the old accuracy gate: the stop event, the lock behind it, the verified trace. #37 dropped that gate, so the guards go too. What stays is what protects the record for a reader: a well-formed graph, verbatim quotes, and the checks on a claimed answer.

## Scope & Constraints

In scope: the eleven decisions under Decisions, the docs and ADRs that describe them, and one rerun of the graph arm.

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
- The claim is `summary.answer`. A patch sets it with the top-level key `answer`. There is no outcome field.

  | State | `audit` checks | Exit code |
  |---|---|---|
  | `answer` is empty | graph, quotes; lists what an answer would still need | 0 |
  | `answer` is set | the above, plus: every accepted goal is answered, the answer and the draft name one candidate per goal, that candidate rests on observations, every test has a result or `not_run` | non-zero if any fails |

- The answer is always named. The rule that a goal's only candidate is its answer goes: a half-finished graph with one candidate would count as a claim.
- The first output line is the status: `no answer claimed`, `answer CS1: checks pass`, or `answer CS1: <n> checks fail`.
- Removed: the commands `stop`, `validate`, `doctor`; the stop event; the refusal of writes after a stop.
- Removed with them: `stop_policy`, `init --strict`, `init --profile`, and every outcome. `init` takes `--goal` and `-o`.
- A failed check of a claimed answer is always an error. There is no warning level.

### 3. The trace is removed

- The state holds no `events`. A state that carries them fails validation.
- A patch holds no `reason`. A patch that carries it is refused.
- `record` and `refresh` no longer compute a digest or log a hand edit. `refresh` still validates, rechecks every quote, and rewrites the HTML and the index.
- The index drops `Last record`.
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
- A new section in `SKILL.md` for a rejected answer, about five lines. One patch carries all of it:
  - what the user said, as an observation with `source: "user"`
  - a `contradicts` edge from it to the rejected candidate
  - a `test` node for each check the guidance asks for, so it shows under `Open` in the index
  - `"answer": ""`, unless the answer stands and only its explanation was rejected
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
  - hints used in the next submit stay at 25 of 25, within noise. The `Last record` line often carried the hint, so a drop points at its removal
  - no rejected answer is repeated
  - tool calls and cost are reported against the notes file ($6.86, 115 calls)

## Progress

- [x] 1. Calls per command. Baseline saved outside git at `test-results/exact-answer/true-detective/loop-usage-s55-loop-r1.txt`
- [x] 2. `audit` replaces `stop`, `validate`, `doctor` (`b15325b`)
- [x] 3. Trace removed (`085981a`)
- [x] 4. Edge ids derived (`4778ec5`)
- [x] 5. `init` output (`21055d7`)
- [x] 6. HTML status line (`3d4d95b`)
- [x] 7. Docs and ADRs, version 0.3.0 (`2312798`, `85dc677`, `920eee8`, `dc7b700`)
- [x] 8. Rerun `s55-loop-r2` and result on #38

## Surprises & Discoveries

Found while preparing the plan, from the transcripts of `s55-loop-r1`:

- **The duplicate-id failures were not a memory problem.** All 12 are `nodes id G1 already exists` in round 1. `init` creates the goal and prints nothing, and the first patch adds it again. 9 cost one extra call, 3 cost three.
- **The 1.3 times target of #38 is probably out of reach by removing friction alone.** Counting the feedback turn, a round of the notes-file arm takes 3.5 tool calls in round 1 and 2.6 later. A round of the graph arm takes 8.1 and 5.3. One of them loads the skill, and at least two are `record` and the final check. Agents already chain the final checks: 41 of the 42 calls that ran `stop` also ran `validate` and `audit`, and 28 of them ran `record` too. So folding the three checks into one saves output tokens more than calls.
- **50 CLI calls failed** in the graph arm, out of about 150. 34 were refused writes after a stop and 12 were `G1`.
- **The package lost about 1000 lines net**: 1429 added, 2444 removed across 75 files. Package checks: 374 passed, 83 subtests.
- **`record` writes `"factors": []`** into a state without groups. It predates this plan and is left alone.
- **`score_ab.py` measures the precision of `solved` stops**, the target #37 dropped. With no stop it prints `no-stop` for every new run. It still scores the old runs, and `score_loop.py` imports its McNemar test. Left alone here; a follow-up can cut it down.

## Decisions

1. `stop` becomes a read-only `audit`. A status computed on demand cannot go stale.
2. `validate` and `doctor` fold into `audit`.
3. The answer is a field set by the patch. It is the claim: `audit` runs the answer checks when it is set.
4. The trace is removed, the patch `reason` with it. Notes about a node go on the node; anything else goes in a file of the agent's own.
5. Ids stay free-form. A counter-based id was dropped.
6. Creation order is the list order. A `step` field and a timestamp were dropped: nothing reads them today.
7. An edge is identified by `from-to`. Checked on 61 states: no pair is used twice and no node id has a hyphen.
8. `init` says what it created. An error naming the next free id was dropped: it would have offered `G2`.

9. `stop_policy` is removed whole: `severity`, `min_viable_candidates`, and with them `init --strict` and `init --profile`. They configured the stop gate, and there is no stop gate. A state that carries `stop_policy` fails validation.
10. There is no outcome. `solved`, `inconclusive`, `blocked`, `budget_exhausted`, `candidate_count_met` and `user_stopped` are all removed. `inconclusive` and `blocked` changed no check, and the reason for giving up is a hypothesis node and a line in the final response. The file alone does not tell "gave up" from "still working".
11. A rejected answer is handled by a convention in `SKILL.md`, with no new field or command. The resume loop is this workflow, so the rerun measures it.

Settled during the implementation:

- One failed check reads `1 check fails`.
- `report.answer` without `summary.answer` fails validation: the HTML would show an answer nothing checked.
- The answer need not name a candidate for an optional goal.
- While no answer is claimed, `audit` prints `needs:` lines for unanswered goals and tests without a result. Grounding is not listed, since it is judged on a named candidate.
- The status counts every error, graph and quote errors included. The answer checks wait for a valid graph.
- An empty patch is refused.
- `refresh` no longer writes the state and lost `-o`. It checks, prints `ok`, and rewrites the two views.
- The schema enforces the hyphen rule too.

`goal_policy` stays. It says which goals need an answer, which the answer checks read.

## Outcomes & Retrospective

Graph arm, the same 14 items, `claude-sonnet-5-5` at high effort, one run per column. The notes file is the run of #37.

| Measure | Notes file | Graph, old CLI (`s55-loop-r1`) | Graph, new CLI (`s55-loop-r2`) |
|---|---|---|---|
| First submit right | 7 | 8 | 6 |
| Passed | 12 | 12 | 10 |
| Submits used | 39 | 39 | 41 |
| Repeated a rejected answer | 0 | 0 | 0 |
| Hints used in the next submit | 20 of 25 | 25 of 25 | 19 of 27 |
| Cost | $6.86 | $12.25 | $11.57 |
| Cost of round 1, mean | $0.27 | $0.49 | $0.36 |
| Cost of a later round, mean | $0.12 | $0.22 | $0.24 |
| Tool calls per round, round 1 | 3.5 | 8.1 | 5.4 |
| Tool calls per round, later | 2.6 | 5.3 | 5.4 |
| CLI calls that failed | | 50 | 37 |
| Writes refused after a stop | | 34 | 0 |
| Hand edits of the state | | 23 | 0 |
| Memory file at the end, median | 2.6 KB | 3.4 KB index, 8.9 KB state | 5.1 KB index, 9.9 KB state |

Reproduce:

    uv run tests/scenarios/exact-answer/score_loop.py test-results/exact-answer/true-detective s55-loop-r2 graph
    uv run tests/scenarios/exact-answer/loop_usage.py test-results/exact-answer/true-detective s55-loop-r2 graph

Against the validation list:

| Check | Result |
|---|---|
| No write refused because of a stop | met: 0 |
| No hand edit of the state | met: 0 |
| No record fails on `G1` | met: 0 |
| No rejected answer is repeated | met: 0 |
| Passed stays at 12 of 14, within noise | 10. Three items passed only before, one only now; McNemar exact p = 0.625. Within noise, but the direction is down |
| Hints used stay at 25 of 25, within noise | not met: 19 of 27, Fisher exact p = 0.004 against the old run |
| Cost against the notes file | 1.7 times, from 1.8 |

What the result says:

- **The friction this plan aimed at is gone.** Round 1 costs 27% less and takes a third fewer calls.
- **Later rounds did not get cheaper.** The total fell by 6%, and this run had two more rounds.
- **The hints were not lost.** In all 8 cases of an unused hint, the hint text is in a node of the graph, and in 5 of them the next answer takes up the subject of the hint. In `dead-mans-island` the hint sat at the top of the index as a test, and the agent drew the opposite conclusion from it.
- **Why fewer hints turned into a covered key point is not known.** Three candidates, which one run per arm cannot tell apart: run-to-run noise (the notes-file arm had 20 of 25 with the hint in its notes), the rejected-answer convention, and the missing `Last record` line. The line is the weakest suspect: the hint sat in the top part of the index about as often in both runs.
- **The 1.3 times target of #38 was not reached**, as the call counts had predicted.

What the 37 failed CLI calls were:

| Count | Error | Kind |
|---|---|---|
| 14 | an answer claimed while a test has no result | the check doing its job; the convention adds a test per check the guidance asks for |
| 10 | `audit --draft answer.md` before `answer.md` exists | friction: the example in `SKILL.md` chains `record` and `audit --draft` |
| 7 | the draft does not name the candidate | the check doing its job |
| 5 | a node id or an edge that already exists | friction |
| 8 | other: a quote that is not verbatim, a schema error, an update of a missing node | mixed |

The counts add to more than 37 because one call can fail on two checks.

Follow-ups, each its own plan:

1. Repeat the rerun once to separate noise from a real drop in hint use and passes.
2. `audit` without `--draft` when no draft exists yet, and an error message for a missing draft file.
3. Cut `score_ab.py` down to what still applies.
4. The presentation eval (#39).
