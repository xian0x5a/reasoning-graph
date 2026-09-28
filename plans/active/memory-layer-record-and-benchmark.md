# Memory layer: cheaper record and a resume benchmark

Tracks issue #37. Decisions are recorded in the #37 comment of 2026-09-28.

## Goal

Make the graph a record that survives context loss, and measure whether it does that better than plain compaction or a plain notes file.

## Intention

#34 and #36 showed the skill does not make answers more accurate. What it does reliably is keep a record. This plan cuts the parts of the record that cost the agent effort without helping a reader, then tests the record as memory.

The memory layer goes first because it is the riskier bet. If the graph cannot beat a notes file, the record should be shaped for people only.

## Scope & Constraints

In scope:

- The record changes listed under Decisions.
- A benchmark loop on True Detective items with three arms.

Out of scope, each a later plan:

- The presentation eval. Its test set is the graphs that stopped `solved` on a wrong answer.
- Subagents handing patch files to the main agent.
- Any long-horizon task beyond the loop below.

Constraints:

- Breaking schema change. No compatibility path for old states; old fixtures are rewritten or removed.
- Package source, schemas and tests stay under `packages/reasoning-graph/`. Skill docs stay under `skills/reasoning-graph/`.
- Benchmark outputs, problem packets, gold files and rubrics stay under ignored `test-results/`. The case texts and solutions come from a third-party site and do not go into git.
- Every arm runs on `claude-sonnet-5-5` at effort `high` through the `claude` harness.

## Work Plan

Milestones 1 to 3 need no change to the package. Milestone 4 is independent of them and only milestone 5 needs both.

### 1. Pilot on Sonnet 5.5

- Run the `no-skill` arm twice per item with `tests/scenarios/exact-answer/run.sh`, on the 60 True Detective packets already built. Run ids `s55-pilot-r1` and `s55-pilot-r2`.
- Select with `score_pilot.py`, same keep rule: keep an item when at least one pilot run is wrong.
- Fewer than 8 kept: build the rest of the pool with `build_items.py` and pilot those too. The source CSV holds 191 cases.

### 2. Rubrics

- Extend `build_items.py` to write the CSV `outcome` column into the spoiler-only `gold.json`.
- Per kept item, write `rubric.json` beside `gold.json`: gold answer, key points, one hint per key point, hints ordered vague to specific. No hint names the culprit.
- A model drafts the rubrics from `outcome`. The author checks each one by hand before any arm runs.

### 3. Loop harness and the two baseline arms

- A driver that runs one item as a multi-turn session: submit, score, hint, compact, retry.
- The agent submits an answer letter plus its reasoning in `answer.md`.
- The scorer is one model call with structured output. The letter is graded by exact match. For each key point the scorer quotes the sentence of the submit that covers it, and the point counts as `covered` only when that quote is found in the submit. It never writes a hint.
- Pass: gold letter and every key point covered. On a fail the driver sends "wrong" plus the pre-written hint for the first failed point.
- Cap per item: key points plus one submits.
- Context reset between submits: the driver ends the session and starts a fresh one. Before the reset the agent writes a handoff summary, which is what a compaction produces, and the driver passes it into the next session. See Surprises & Discoveries for why this replaces a real compaction.
- Every arm gets the handoff summary, as it would in real use. The arms differ in what else survives on disk.
- Arms: `compaction-only` keeps nothing else. `notes-file` also keeps `notes.md`, which the agent is told to maintain and reread.
- Validate the scorer on the #34 answers before running any arm.

### 4. Record changes in the package

Tests first for each step, seen failing for the expected reason. Deletions come first so later steps touch less code.

1. **Remove the reviewer and the threshold.** `review`, `stop-review`, `require_review`, the stale-review check, `belief_threshold`. `stop` keeps the mechanical checks: verbatim quotes, every test has a result or `not_run`, the answer names a candidate.
2. **Remove `posterior`.**
3. **1–5 scale with defaults.** One optional `score` on claims and on evidence edges. Observation defaults to 5, open hypothesis and candidate to 3, edge to 3. The CLI maps the scale to numbers through one named table.
4. **Correlation groups.** A group is a list of edge ids plus one combined score.
5. **`note` replaces `reasoning`.** Optional on edges, the same field nodes have.
6. **Belief leaves the state.** `record` stops writing `belief`. `render.py` computes the ranking at render time. The `beliefs` command is removed. The HTML marks an answer that is not the top-ranked candidate; the agent is not warned.
7. **Index file.** `record` refreshes `<state>.index.md` beside the state: one line per node and edge, open hypotheses and `not_run` tests first, no quotes.
8. **Docs.** `SKILL.md`, `docs/driver.md`, `docs/cost-model.md`, `docs/schema/factors.md`, and new ADRs replacing 0003, 0004 and 0007.

Modules touched, from a field-usage grep: `costs.py`, `validation.py`, `policy.py`, `cli.py`, `render.py`, `offline_render.py`, `state.py`, `models.py`, `audit.py`, `events.py`, `visual_factors.py`, both schemas.

### 5. Graph arm and result

- Run the `graph` arm through the same driver. It gets the handoff summary and keeps `state.json` plus the index.
- Score all three arms and post the result on #37.

## Validation

Package checks:

    uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q

Behavior worth a test:

- A score outside 1–5 is rejected.
- A claim or edge with no score takes its default.
- A state written by `record` holds no computed belief.
- `record` refreshes the index, and open hypotheses and `not_run` tests come first in it.
- `stop` passes with no review recorded, and still fails on a bad quote or a test with no result.
- A correlation group counts its edges once, at the combined score.

Scorer checks, on the #34 answers:

- It fails every answer with a wrong letter.
- It gives the same verdict three times in a row on the same submit.

Benchmark metrics:

| Metric | Answers |
|---|---|
| First-submit accuracy, exact match | Does the skill hurt accuracy? |
| Submits until pass | Does the record help recovery? |
| Repeated rejected answers | Did memory survive compaction? |
| Hints kept after compaction | Same, for facts |
| Cost per run | Is a checkpoint cheap enough? |

Accuracy guard, fixed before any run: the skill hurts when no-skill-only-right exceeds skill-only-right with McNemar p < 0.10. This is the `score_ab.py` rule read in reverse. The `compaction-only` arm's first submit is the no-skill answer, so the guard needs no fourth arm.

## Progress

- [x] Decisions recorded on #37
- [x] 1. Pilot on Sonnet 5.5: 97 of 120 runs correct, 15 of 60 items kept, 8 of them wrong in both runs. Cost $13.54.
- [ ] 2. Rubrics: 15 drafted, hand check pending
- [ ] 3. Loop harness and baseline arms: scorer and driver written; the driver has not completed a run
- [ ] 4. Record changes
- [ ] 5. Graph arm and result

## Surprises & Discoveries

- `run.sh` passes `--no-session-persistence`, and every run is a single turn. The loop needs a session that continues across submits, so the driver cannot reuse `run_claude` as it is.
- Headless `claude -p` has no documented way to force a compaction. `/compact` is not listed as available in print mode, no flag or setting lowers the auto-compact threshold, and the stream-json docs name no compaction event, so a run could not prove one happened. Sources: `https://code.claude.com/docs/en/headless.md`, `https://code.claude.com/docs/en/sessions.md`. The driver therefore emulates compaction with a handoff summary and a fresh session, which also works on any harness.
- Sessions can continue across `claude -p` calls with `--resume <session-id>`, but not with `--no-session-persistence`. The emulated reset does not need this.
- The first scorer failed its stability check. On Sonnet 5.5 the same submit passed three times and failed twice. Two changes fixed it on the probe item: a key point counts as covered only when the scorer quotes the covering sentence and that quote is found in the submit, and the scorer runs on `claude-opus-5-5`. Five repeats then agreed on a right and on a wrong answer. This is one item; the check is repeated on every kept item before an arm runs.
- The verdict is covered or missing. `contradicted` is dropped, since the driver treats both failures the same.
- The first loop run was stopped by Sonnet 5.5's safeguards, category `reasoning_extraction`, before the agent did any work. The flagged message was the new arm prompt, which asks for the reasoning above the answer and says it is graded. The pilot prompt, which asks to "explain why leading alternatives lose", ran 121 times without a flag. No reworded prompt was tried; the arm prompt wording is an open decision.
- The rubric drafter fills its maximum: all 15 rubrics have 4 key points. Six hints in five rubrics name the gold suspect, against the drafting rule.
- Risk: the items are small. A handoff summary may carry every hint and rejected answer, and then the three arms tie. A tie is a real result: on tasks this size the memory layer adds nothing over compaction.
- ADR 0001 and 0002 are already superseded. Only 0003, 0004 and 0007 are live and affected.
- Agents already write tiers. Across 262 graphs in `test-results/`, 93% of observation priors sit in 0.80–0.95, and edge ratios cluster on 1.2, 1.3, 1.5, 2 and 3.

## Decisions

| Decision | Reason |
|---|---|
| Memory layer before presentation | Riskier bet, and its eval can be scripted |
| Scores stay, on a 1–5 scale | A reader catches a wrong weight more easily; decimals claimed a calibration that #36 showed does not exist |
| Defaults, scores only on exceptions | Most written scores were boilerplate |
| Belief threshold dropped | It drove the tuning records, 0.64 per run |
| Correlation groups kept, simplified | Without them correlated clues count twice |
| `note` replaces `reasoning`, no enforced guard | `reasoning` is 45% of edge bytes; a forced note would push scores toward the default |
| Reviewer machinery removed | Not what the skill is about; a same-model reviewer shared the misreading |
| Computed belief out of the state, `posterior` removed | The agent does not act on it, and seeing it enables tuning |
| Main agent is the only writer | `record` rewrites the whole state; two writers lose updates |
| Index file refreshed by `record` | Cheap reread, the resume entry point, and the subagents' read view |
| Checkpoint timing left to the agent | No enforced budget |
| True Detective with a scorer loop | A long-horizon task costs too much for now; the loop stretches the run and hints add information only the conversation holds |
| Three arms | A notes file is the honest rival of a graph |

Proposed scale table, to confirm in step 4.3. The edge values are the ratios agents already wrote most.

| Score | Claim probability | Edge ratio, `supports` |
|---|---|---|
| 1 | 0.1 | 1.2 |
| 2 | 0.3 | 1.5 |
| 3 | 0.5 | 2 |
| 4 | 0.7 | 3 |
| 5 | 0.9 | 5 |

`contradicts` uses the reciprocal.

## Outcomes & Retrospective

Not started.
