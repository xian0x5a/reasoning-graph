---
name: reasoning-graph
description: >
  Use when solving complex reasoning problems where observations, hypotheses,
  tests, and candidate answers can diverge. Keeps a JSON reasoning graph as
  working memory, gates the final answer on recorded evidence, and renders a
  live HTML view of progress.
---

# Reasoning Graph

Use this skill when a messy task is worth keeping what you have seen, suspected, and tested in one explicit record: puzzles, root-cause analysis, ambiguous debugging, planning under uncertainty. If the task does not justify that overhead, do not use this skill.

The graph does three jobs:

- **Memory:** `state.json` holds observations, hypotheses, tests, and candidate answers, so progress survives long runs and lost context. Read it to recall where you are.
- **Stop gate:** `stop` accepts a confident answer only when it rests on recorded observations and an independent reviewer has passed the graph.
- **Progress view:** every `record` refreshes `state.html` beside the state for a human to follow.

The graph does not choose your next step. Work the problem however you judge best; the graph keeps the record.

Requirements: the helper CLI, installed separately (if `reasoning-graph --help` is unavailable, see `docs/install.md`), and a subagent backend for the reviewer. Without a subagent backend, do not use this skill.

## Workflow

1. **Frame the goal** with `init`. Add epistemic/blocker goals only when the user or task wording accepts them.
2. **Record at checkpoints.** A checkpoint is where the work turns: sources read, a candidate answer formed, a test result in, a review's findings fixed. Put everything since the last checkpoint in one patch, and write it before moving on; a graph filled in after solving leaves a story, not a record.
3. **Draft the answer** in `answer.md` once a candidate looks ready.
4. **Get it reviewed.** Start a reviewer subagent (below). On `fail`, record all the fixes in one patch and review again; any `record` after a review makes it stale.
5. **Stop** when a gate below holds, run the final checks, and give the answer.

Mutating commands rewrite the input state file by default; use `-o <path>` for a separate output file or `-o -` for stdout.

```bash
reasoning-graph init --goal "<goal>" --strict -o state.json
# once per checkpoint; refreshes state.html
reasoning-graph record state.json --patch - <<'JSON'
{"reason": "...", "nodes": [...], "edges": [...]}
JSON
# the reviewer subagent runs: reasoning-graph review state.json --reviewer <its agent id> --verdict pass|fail --findings "<what it checked and found>"
reasoning-graph stop state.json --outcome solved --reason "<gate that fired>" -o state.stopped.json \
  && reasoning-graph validate state.stopped.json \
  && reasoning-graph audit state.stopped.json \
  && reasoning-graph stop-review state.stopped.json --draft answer.md
```

Pass each patch on stdin as above rather than writing a patch file first: one tool call per record. Chain the final checks with `&&` so the first failure stops the chain.

Record patch:

```json
{
  "reason": "Read the maintenance log",
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Pump P2 restarted twice before the outage", "source": "maintenance.log line 40", "quote": "P2 restarted 02:10, 02:14 (cause unknown)", "prior": 0.95},
    {"id": "H1", "type": "hypothesis", "text": "P2 restarts caused the outage", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Compare the outage start with the restart times"}
  ],
  "edges": [
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "likelihood_ratio": 2, "reasoning": "Restarts just before an outage are more likely if they caused it."},
    {"id": "H1-T1", "from": "H1", "to": "T1", "type": "prompts", "reasoning": "The claim suggests a timing check."}
  ]
}
```

`reason` says what the checkpoint did and becomes the progress log. One patch carries every kind of change:

- **Add:** `nodes`, `edges`, `factors` (a factor whose `id` exists replaces it).
- **Change:** `update_nodes` and `update_edges`, each item `{"id": "H1", "set": {"prior": 0.3}, "unset": ["posterior"]}`. A node's `id`/`type` and an edge's `id`/`from`/`to` are fixed; remove and re-add instead.
- **Remove:** `remove_nodes` (takes the node's edges with it), `remove_edges`, `remove_factors`.

Make every change through a patch. After editing `state.json` by hand, run `record` with a patch holding only `reason` (what you edited): it rechecks every quote, recomputes beliefs, logs removed objects, and makes an earlier review stale.

## Recording

- **Observations cite their source.** Set `source` to where the fact came from (file and line, section, URL, command); for a local file, start `source` with its path. When the source is text, set `quote` to the exact excerpt, hedges included ("may", "expert needed", "not checked"); join separate excerpts with `...`. `record` rejects a quote that is not verbatim in the local file its `source` names. An observation claims no more than its quote.
- **Checks you cannot run are marked, not answered.** Add a `test` node for each check that would settle a claim, even one nobody can run here (a lab exam, an interview, forensics on a case file). Set `not_run` on it to the reason; it then needs no result, cannot have one, and shows as "not run" in the view. Never write a result for a check that did not happen.
- **Tests get results.** A run test records what came back as an `observation` linked `test --leads_to--> observation`, which then `supports`/`contradicts` the claim it tested. A failed or inconclusive probe is still a result, and so is "not run: made moot by O7". A conclusion drawn from a result is a separate `hypothesis` linked by `leads_to` from the observation. Shapes: `docs/schema/tests.md`.
- **Alternatives are your call.** Add competing hypotheses or candidates when the choice between them matters to you or the task asks for alternatives; no gate counts them.
- **Notes are your memory.** Any node may carry a `note`: caveats, what is left to check, why an inference holds, anything you want to find again when you reread the state.
- **One node per claim for its whole life:** update it with `update_nodes` as evidence arrives instead of adding a second node for the proved form.

## Subagents

The reviewer is required (see Review). Other delegation is optional: bounded probes (source research, file inspection, test runs, verification) when that saves context or time; independent probes can run in parallel. The main agent owns the graph: it reviews each child's report and records accepted results itself. Ask children for observations with source refs and quotes, and for every interpretation they tried, failures included.

## Stop gates

`init --strict` sets `stop_policy.belief_threshold: 0.8`. A `solved` or `candidate_threshold_met` stop is accepted only when:

- every accepted goal has a `candidate_solution` answering it (or is listed in `goal_policy.optional_goals`)
- the best candidate is evidence-grounded: all of its `leads_to` premises are grounded, or its evidence favors it (net likelihood ratio > 1) counting `supports` only from grounded sources and `contradicts` from any source; observations are the base, and priors or posteriors never ground a claim
- its belief reaches `belief_threshold`
- every `test` node has a result observation or a `not_run` reason
- the latest review passed and no `record` came after it (`require_review`)

Otherwise stop with `inconclusive`, `budget_exhausted`, or `blocked` and report the open hypotheses. The stop reason names the gate that fired.

- A hypothesis that wins by elimination needs that elimination recorded as positive evidence: an observation such as "H2 ruled out" that `supports` the survivor, or a `leads_to` premise from it. Contradicting its siblings does not raise the survivor's belief.
- Ask the user before deepening search when remaining work would cost meaningful time.

## Beliefs

`prior` is local input, `belief` is computed output, `posterior` is an explicit override that bypasses the node's inputs until removed. `record` writes each claim's current `belief` into the state: read it there, never set it. Claims need a prior, a posterior, belief-bearing `leads_to` premises, or a calibrated joint factor. Goals, constraints, and tests carry no score. Evidence from a hypothesis or candidate is scaled by its belief, support from an ungrounded claim has no effect, and evidence cycles between claims are invalid. Read `docs/cost-model.md` before assigning likelihoods.

Use coarse numbers.

## Review

Before stopping, start an independent reviewer subagent. Give it the state path, the draft answer, and the sources; not your reasoning. It checks:

1. **Observations against sources:** each observation the answer relies on says no more than its `quote` and `source`; no hedge dropped out. Text that reports an action, test, or finding its quote does not describe is a fail.
2. **Answer against graph:** every factual claim in the answer traces to an observation; the answer adds nothing the graph lacks.
3. **Evidence against the answer:** anything in the sources that cuts against it is recorded, and the answer addresses it.

The reviewer does not edit the graph. It records its own verdict with `review`, naming itself and listing what it checked and found. On `fail`, fix the graph with one `record` and the draft, then start a fresh review.

After `stop`, run `validate`, `audit`, and `stop-review --draft answer.md`, and fix every required fix.

## Schema quick reference

Validate real files with `reasoning-graph validate`. Machine-readable contracts: `reasoning-graph schema state` and `reasoning-graph schema patch`.

Node types:

- `goal` — target to prove, solve, decide, or explain
- `observation` — what was seen, given, verified, or source-backed, recorded as observed rather than interpreted; `prior` accounts for observation/transcription/source reliability
- `constraint` — boundary valid answers must satisfy; connect with `requires`
- `hypothesis` — claim not yet established: an interpretation, an intermediate step toward the goal, or a blocker backed by observations. Carries `prior` while open and `leads_to` premises once proved
- `test` — action/check/procedure; carries no score until its result `observation` is recorded
- `candidate_solution` — possible answer; requires `answer_kind` and a `candidate_solution -> goal` `answers` edge

Edge types (every edge needs nonblank `reasoning`, one to five sentences):

- `requires` — hard dependency; prefer `goal -> constraint` or `candidate_solution -> constraint`
- `supports` — positive belief update; numeric form uses `likelihood` or `likelihood_ratio > 1`
- `contradicts` — negative belief update; numeric form uses `likelihood` or `0 < likelihood_ratio < 1`; lowers belief but does not disqualify the target by itself
- `prompts` — non-evidential provenance from a claim to a test or follow-up; no belief update
- `leads_to` — premise/dependency used to derive a target's base belief
- `answers` — candidate satisfies a goal; must be `candidate_solution -> goal`

Factors (`docs/schema/factors.md`): incoming numeric edges to one target that share a source, observation, latent cause, or logical overlap are aggregated in one factor instead of multiplied as independent evidence. `leads_to` factors use `aggregation: {"kind": "joint_probability", "probability": ...}`; `supports`/`contradicts` factors use `aggregation: {"kind": "likelihood", "if_target_true": ..., "if_target_false": ...}`.

Goals and candidates (`docs/schema/goals.md`):

- `answer_kind` values: `exact_answer`, `exact_method`, `method_hypothesis`, `clue_path`, `blocker`. For concrete solve goals only `exact_answer` and `exact_method` may answer the accepted goal.
- "Not solved", "cannot establish", or "missing dependency" is a stop outcome or hypothesis blocker, not a candidate, unless the user accepted an epistemic/negative goal.
- Use multiple `goal` nodes only when the user accepts multiple outcomes. Chained sub-goals are `goal` nodes linked `parent --requires--> child`; a goal is answered only when a candidate answers it and every required sub-goal is answered.

Report (`docs/schema/reporting.md`): `summary.answer`, `report.answer`, and the final draft must name the best candidate of each accepted goal by id or exact text; an answer matching no candidate fails `stop-review`. Keep ranking words like `Best` or `rejected` out of node text.

## Output

Default final response: the answer, a concise proof path citing sources, open hypotheses relied on, alternatives when the task asks for them or ambiguity matters, and the next test if uncertainty remains. Present a user-facing proof path, not raw graph state. Include the path to `state.html`.

## Reference docs

- `docs/schema/tests.md` — test lifecycle and result observation pattern
- `docs/schema/goals.md` — candidate, answer-kind, multiple-goal, and lemma rules
- `docs/schema/factors.md` — `factors` examples and validation rules
- `docs/schema/reporting.md` — report and presentation metadata
- `docs/cost-model.md` — belief math and likelihoods
- `docs/driver.md` — CLI commands, state JSON, events, audit, and stop-review mechanics
- `docs/rendering.md` — graph/HTML rendering options
- `docs/install.md` — one-time helper CLI install
