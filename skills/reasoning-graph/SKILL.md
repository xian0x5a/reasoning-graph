---
name: reasoning-graph
description: >
  Use when solving complex reasoning problems where observations, hypotheses,
  tests, and candidate answers can diverge. Keeps a JSON reasoning graph as
  working memory, checks the claimed answer against recorded evidence, and
  renders a live HTML view of progress.
license: MIT
---

# Reasoning Graph

Use this skill when a messy task is worth keeping what you have seen, suspected, and tested in one explicit record: puzzles, root-cause analysis, ambiguous debugging, planning under uncertainty. If the task does not justify that overhead, do not use this skill.

The graph does three jobs:

- **Memory:** `state.json` holds observations, hypotheses (the candidate answers among them), and tests, so progress survives long runs and lost context. To recall where you are, read `state.index.md` first: one line per node and edge, with what is still open on top. Open `state.json` only for a quote or a field the index leaves out.
- **Answer check:** `audit` checks the answer you claim: it must rest on recorded observations and every test must have a result.
- **Progress view:** every `record` refreshes `state.html` beside the state for a human to follow, and `state.index.md` for you.

The graph does not choose your next step. Work the problem however you judge best; the graph keeps the record.

Requirements: the helper CLI, installed separately (if `reasoning-graph --help` is unavailable, see `docs/install.md`).

## Workflow

1. **Frame the goal** with `init`. It creates the goal node `G1`; do not add it again. Add epistemic/blocker goals only when the user or task wording accepts them.
2. **Record at checkpoints.** A checkpoint is where the work turns: sources read, a candidate answer formed, a test result in. Put everything since the last checkpoint in one patch, and write it before moving on; a graph filled in after solving leaves a story, not a record.
3. **Claim the answer** with `"answer"` in a patch, run `audit`, and fix what it reports. Then give the answer.

```bash
reasoning-graph init --goal "<goal>" -o state.json
# once per checkpoint; refreshes state.html and state.index.md
reasoning-graph record state.json --patch - <<'JSON'
{"nodes": [...], "edges": [...]}
JSON
# the last patch names the answer; audit writes nothing
reasoning-graph record state.json --patch - <<'JSON' && reasoning-graph audit state.json
{"nodes": [...], "edges": [...], "answer": "H2"}
JSON
```

Pass each patch on stdin as above rather than writing a patch file first: one tool call per record. `record` rewrites the state file in place.

Record patch:

```json
{
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Pump P2 restarted twice before the outage", "source": "maintenance.log line 40", "quote": "P2 restarted 02:10, 02:14 (cause unknown)"},
    {"id": "H1", "type": "hypothesis", "text": "P2 restarts caused the outage", "score": 2, "note": "P2 restarts weekly without an outage."},
    {"id": "T1", "type": "test", "text": "Compare the outage start with the restart times"}
  ],
  "edges": [
    {"from": "O1", "to": "H1", "type": "supports"},
    {"from": "H1", "to": "T1", "type": "prompts"}
  ]
}
```

One patch carries every kind of change:

- **Add:** `nodes`, `edges`, `factors`, `exclusive_sets` (a group or set whose `id` exists replaces it).
- **Change:** `update_nodes` and `update_edges`, each item `{"id": "H1", "set": {"score": 4}, "unset": ["note"]}`. A node's `id`/`type` and an edge's `from`/`to` are fixed; remove and re-add instead.
- **Remove:** `remove_nodes` (takes the node's edges with it), `remove_edges`, `remove_factors`, `remove_exclusive_sets`.
- **Claim:** `answer` names the answer; `""` withdraws it.

An edge has no id of its own. Name it by its ends, as `O1-H1`, in `update_edges`, `remove_edges`, and groups. One edge per ordered pair, and no hyphen in a node id.

Make every change through a patch. For what a patch cannot reach (`goal_policy`, a bulk rewrite), edit `state.json` by hand, then run `reasoning-graph refresh state.json`: it checks the edit as it would a patch and rewrites the views.

## Recording

- **Observations cite their source.** Set `source` to where the fact came from (file and line, section, URL, command); for a local file, start `source` with its path. When the source is text, set `quote` to the exact excerpt, hedges included ("may", "expert needed", "not checked"); join separate excerpts with `...`. `record` rejects a quote that is not verbatim in the local file its `source` names. An observation claims no more than its quote.
- **Checks you cannot run are marked, not answered.** Add a `test` node for each check that would settle a claim, even one nobody can run here (a lab exam, an interview, forensics on a case file). Set `not_run` on it to the reason; it then needs no result, cannot have one, and shows as "not run" in the view. Never write a result for a check that did not happen.
- **Tests get results.** A run test records what came back as an `observation` linked `test --yields--> observation`. A failed or inconclusive probe is still a result, and so is "not run: made moot by O7". Link the result to the claim it tested, and to any conclusion drawn from it (a separate `hypothesis`), by what it means: choosing the edge, below. Shapes: `docs/schema/tests.md`.
- **Alternatives are your call.** Add rival answers or rival hypotheses when the choice between them matters to you or the task asks for alternatives; no check counts them. A candidate answer is a hypothesis with an `answers` edge to the goal it would settle, and its text states the whole claim: answering "who killed Bryan?", each rival answer is one hypothesis such as "Thornton killed Bryan". A hypothesis the answer depends on, such as how it was done, a motive, or that a rival is excluded, answers no goal, or only a sub-goal it settles. When at most one of a set of rivals can be true, list them in an exclusive set (below).
- **Notes are your memory.** Any node or edge may carry a `note`: caveats, what is left to check, why an inference holds, anything you want to find again when you reread the state. Write one on an edge when its score departs from the default or the link is not obvious from the two texts. What concerns no node goes in a file of your own.
- **One node per claim for its whole life.** Update it with `update_nodes` as evidence arrives instead of adding a second node for the proved form, and add an `answers` edge when it turns out to settle a goal. Evidence that a candidate is the answer goes on the candidate; evidence about a step it needs, a motive, or how it was done goes on the hypothesis that states that step. When two nodes state one claim, merge them: give the node you keep the other's edges (where a source has an edge into both, keep the one into the node you keep) and its place in any group or exclusive set, put its reasons in the kept node's `note`, and remove the other, all in one patch.

## Subagents

Delegation is optional: bounded probes (source research, file inspection, test runs, verification) when that saves context or time; independent probes can run in parallel. The main agent is the only writer of the graph: it reviews each child's report and records accepted results itself. Point children at `state.index.md` to read what is known and open. Ask them for observations with source refs and quotes, and for every interpretation they tried, failures included. A check handed to a child is a `test` node; mark it `not_run` if it does not come back.

## Answer checks

`audit` is read-only and prints the status on its first line: `no answer claimed`, `answer H2: checks pass`, or `answer H2: 2 checks fail`. It always checks that the graph is well-formed and every quote is verbatim. Once an answer is claimed it also checks that:

- every accepted goal has a candidate answering it (or is listed in `goal_policy.optional_goals`)
- `answer` names exactly one candidate per goal, by its id. A goal's only candidate is not the answer until you name it
- the answer candidate is evidence-grounded: all of its premises are grounded, or its evidence favors it on balance, counting `supports` only from grounded sources and `contradicts` from any source; observations are the base, and a score never grounds a claim
- every `test` node has a result observation or a `not_run` reason

No belief level and no ranking is checked: the answer is the candidate you name, not the one that scores highest.

- If the evidence does not decide it, or you are blocked, claim no answer. Record the blocker as a hypothesis and report the open hypotheses.
- A hypothesis that wins by elimination needs that elimination recorded as positive evidence: an observation such as "H2 ruled out" that `supports` the survivor, or a `premise_of` edge from it as choosing the edge (below) describes. Contradicting its siblings does not ground the survivor.
- The CLI checks the record, not your reading of the sources: before claiming, reread each observation the answer relies on against its `quote`, and look for evidence in the sources that cuts against the answer.
- Ask the user before deepening search when remaining work would cost meaningful time.

## Review before claiming

The scores and edges are yours, and so are their mistakes: an observation every rival explains scored as support, clues sharing one cause left ungrouped, corroboration recorded as a deduction, one claim recorded as two nodes. `audit` checks none of that, and you do not read the computed beliefs. When a subagent is available and the answer matters, hand the state to a read-only reviewer with the brief in `docs/review.md` before claiming. It reads the rendered beliefs and reports facts about the evidence, never a number or which way to move one. Apply what you accept in one patch, then claim. One round per answer: the review is a second reading, not a gate to pass.

## When the answer is rejected

Keep working in the same state; nothing locks it. Put the rejection in one patch:

- what the user said, as an observation with `"source": "user"`
- a `rules_out` edge from it to the rejected candidate; use `contradicts` instead when the user only doubts it
- a `test` node for each check the guidance asks for, so it shows under `Open` in the index
- `"answer": ""`, unless the answer stands and only its explanation was rejected

## Scores

`score` is the only number you write, from 1 to 5, on claims and on `supports`/`contradicts` edges. Leave it out unless the default is wrong:

| score | claim | evidence edge (likelihood ratio) |
| --- | --- | --- |
| 1 | very unlikely | ×1.2 |
| 3 | open | ×2 |
| 5 | well established | ×5, the ceiling: stronger evidence still counts ×5; never proof |

Defaults: observation 5, hypothesis 3, evidence edge 3. A claim with premises carries no score (choosing the edge, below), and neither do goals, constraints, and tests.

An evidence edge is a likelihood ratio: how much more expected the observation is if the target is true than if it is false. It measures diagnosticity, not relevance. An observation that every rival explains about as well as the target is about as expected either way: a likelihood ratio near 1, so draw no edge. One that fits the target and some rivals but not the rest is still evidence for each claim it fits; the more rivals it also fits, the closer its ratio is to 1. An unscored edge still counts as score 3, ×2. A `contradicts` edge takes the reciprocal.

Score what you judge and move on. The CLI turns scores into a belief per claim only when it renders the graph, so a reader can see why one candidate outranks another and catch a weight that looks wrong. The state holds no belief, and the commands of the workflow (`record`, `refresh`, `audit`) print none. Evidence cycles between claims are invalid. Details: `docs/cost-model.md`.

## Schema quick reference

Machine-readable contracts: `reasoning-graph schema state` and `reasoning-graph schema patch`.

Node types:

- `goal` — target to prove, solve, decide, or explain
- `observation` — what was seen, given, verified, or source-backed, recorded as observed rather than interpreted; lower its score only when the reading itself is doubtful; put that doubt into its evidence edges' scores too, since an observation's score weighs only on the claims it is a premise of
- `constraint` — boundary valid answers must satisfy; connect with `requires`
- `hypothesis` — claim not yet established: an interpretation, an intermediate step toward the goal, a candidate answer (it has an `answers` edge), or a blocker backed by observations. Open until it has premises or is ruled out
- `test` — action/check/procedure; carries no score until its result `observation` is recorded

Edge types (any edge may carry a `note`):

- `requires` — hard dependency; prefer `goal -> constraint`, or a candidate's `hypothesis -> constraint`
- `supports` — evidence for the target, at its `score` or the default; each edge multiplies the target's odds
- `contradicts` — evidence against the target, at its `score` or the default; does not disqualify the target by itself
- `prompts` — non-evidential provenance from a claim to a test or follow-up
- `premise_of` — the source is a premise the target stands or falls with (choosing the edge, below): the target takes its belief from all its premises jointly and carries no score; `supports` edges into it apply on top. Must run from an observation or hypothesis into a `hypothesis`
- `yields` — from a test that ran to the observation of its result. Must be `test -> observation`; carries no belief; a `not_run` test has none
- `answers` — if the source holds, the goal is settled; this makes the source a candidate answer. Must be `hypothesis -> goal`, the only edge from a hypothesis to a goal, and carries a required `answer_kind` (goals and candidates, below): `{"from": "H2", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}`
- `rules_out` — an observation that settles a claim as false: a user's rejection, a failed check the claim cannot survive. Must be `observation -> hypothesis`, takes no score, and caps the claim's belief below 1% whatever supports it, along with every claim resting on it as a premise. `audit` fails an answer that names a ruled-out claim. Undo it by changing the edge to `contradicts`

Choosing the edge: the type decides which way belief moves. Ask whether the target stands or falls with its sources: certain if they all hold, and left without a basis if any one of them fails.

- Stands and falls with them: each is a premise, linked `premise_of`. The target's belief starts from theirs jointly, so each added premise can only lower it, and it carries no score: unset any score it had in the patch that adds its premises. A claim that combines others stands or falls with them, and so does a claim a test result proves, even when clues also support it: they stay evidence on top.
- Falls with them, but they would not make it certain: keep them as premises and add what is missing as a premise of its own, a hypothesis; for an elimination, that the listed rivals are all there are. That hypothesis rests on its score alone until evidence supports it; until then the target is not grounded through its premises, and `audit` fails an answer resting on it.
- Survives losing one of them, because another source still settles it or it never needed that one (a second proof, one of several alternatives, a corroborating clue): that one is evidence, `supports` or `contradicts` scored by its likelihood ratio, so each one adds. As premises they would multiply, and every extra one would lower the target. An observation that would make the target certainly false takes `rules_out`.

Put evidence about one part of a combined claim on that part. Belief flows only from sources to targets, so evidence on the combined claim never reaches its parts and lifts the claim above them.

Correlation groups (`docs/schema/factors.md`): edges into one target that share a source, observation, latent cause, or logical overlap count once. List them in one `factors` item with a combined score, `{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4}`; the grouped edges carry no score of their own.

Exclusive sets: claims of which at most one can be true, such as rival answers or rival explanations of one event, `{"id": "X1", "members": ["H1", "H2", "H3"]}` in `exclusive_sets`. Members are hypotheses; the set need not list every possibility. A set changes no belief; it tells the reader of the page when two members are both likely, which means a score or edge among them is wrong, or the evidence has not separated them yet.

Goals and candidates (`docs/schema/goals.md`):

- `answer_kind` on each `answers` edge: `exact_answer`, `exact_method`, `method_hypothesis`, `clue_path`, `blocker`. For concrete solve goals only `exact_answer` and `exact_method` may answer the accepted goal. A hypothesis that answers two goals gives each edge its own kind.
- "Not solved", "cannot establish", or "missing dependency" is a blocker hypothesis that answers no goal, unless the user accepted an epistemic/negative goal.
- Use multiple `goal` nodes only when the user accepts multiple outcomes. Chained sub-goals are `goal` nodes linked `parent --requires--> child`; a goal is answered only when a candidate answers it and every required sub-goal is answered.

The state is the graph: there is no report section. Keep ranking words like `Best` or `rejected` out of node text; the rank is computed when the graph renders.

## Output

Default final response: the answer, a concise proof path citing sources, open hypotheses relied on, alternatives when the task asks for them or ambiguity matters, and the next test if uncertainty remains. Present a user-facing proof path, not raw graph state or the index. Include the path to `state.html`.

## Reference docs

- `docs/schema/tests.md` — test lifecycle and result observation pattern
- `docs/schema/goals.md` — candidate, answer-kind, multiple-goal, and lemma rules
- `docs/schema/factors.md` — correlation groups
- `docs/cost-model.md` — score tables, defaults, and the belief math behind the rendered view
- `docs/review.md` — brief for the optional pre-claim reviewer
- `docs/driver.md` — CLI commands, state JSON, the index file, and audit
- `docs/rendering.md` — graph/HTML rendering options
- `docs/install.md` — one-time helper CLI install
