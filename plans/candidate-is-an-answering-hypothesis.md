---
status: active
---

# A candidate is a hypothesis that answers a goal

## Goal

Remove the `candidate_solution` node type. A candidate answer is a `hypothesis` with an `answers` edge to the goal it settles, and `answer_kind` moves onto that edge. One breaking change across schema, package, page, skill docs, tests, and fixtures, with no compatibility path.

## Intention

The type carries no math: a candidate and a hypothesis share their default score, their edges, and the belief walk. What the type does is split one claim in two. The writer records an answer label ("Randy") as a candidate and the claim it reasons about ("Randy did it") as a hypothesis, and the evidence divides between them (issue #8, ADR 0018). It also blocks one node per claim for its whole life: a lemma that turns out to settle a sub-goal has to be recreated as a candidate.

With candidacy as an edge, a claim becomes an answer by gaining an `answers` edge and stays the same node. A council of Opus, DeepSeek, and Sonnet (two rounds, 2026-11-16) agreed to adopt it with the changes below, at 0.75 to 0.8 confidence.

## Scope & Constraints

- Node types: `goal`, `observation`, `constraint`, `hypothesis`, `test`. `candidate_solution` is removed, without aliases.
- `answers` must run `hypothesis -> goal`, carries a required `answer_kind` with no default, checked against the goal as today. It is the only edge from a hypothesis to a goal (ADR 0005's rule, inverted). One hypothesis may answer two goals, each edge with its own kind.
- Node text is the full claim ("Thornton killed Bryan"), not a bare label: a label beside a claim re-creates the split.
- `summary.answer` names each answer by id, as a whole word. The exact-text match goes: "Thornton" matches inside "Sergeant Josiah Thornton", "42" inside "142".
- Usage rule in the skill: `answers` means "if this claim holds, the goal is settled". A step answers a sub-goal it settles, or nothing.
- The one-node and merge rules stay; a merge keeps either node, since neither has a type the other lacks.
- Every rule keyed on the type is re-keyed on the edge: answer checks, ranked candidates, goal targets, the unresolved-outcome heuristic, page badge, filter, and rank note, Mermaid and SVG clusters, `premise_of`/`rules_out`/exclusive-set endpoints, default scores.
- ADR 0019 amends 0005 (the edge rule) and 0018 (merge target).
- Old state files fail validation; regenerate them. Package version bumps.

## Work Plan

1. **Probe gate (text only).** Write the B-model SKILL.md, commit, and run a first-patch probe against the branch head under one variant-neutral judge: "answer nodes" are nodes with an `answers` edge to a goal, whatever their type, so both models are judged by one prompt in one run. The judge reports, per patch: pairs of nodes stating one claim (one of them an answer node), answer nodes whose truth would not settle the goal they answer, and answer nodes written as bare labels. Pass when, against the branch head in the same run, B has no more patches with a restated claim and no more than 2 extra patches with a misplaced `answers` edge. A fail stops the work and goes back to the user with the data.
2. **Package.** Schema, models, validation, policy, costs, case, index, page, graph view, Mermaid, offline render, CLI messages. Remove the type and every branch on it.
3. **Docs.** SKILL.md (already from 1), `docs/schema/goals.md`, `driver.md`, `cost-model.md`, `review.md`, `rendering.md`, README, ADR 0019, scenario templates.
4. **Tests** by an independent agent: behaviour of the new edge rules, answer checks naming by id, a candidate gaining `answers` mid-run, page and index output; fixtures rewritten.
5. **Final review** by another independent agent; fix; commit.

## Progress

- [x] 1 Probe gate: passed. `answers_probe.py` under `~/.agents/artifacts/outputs/reasoning-graph/2026-11-16/candidate-as-hypothesis/`, 4 samples x 14 items, 46 judged patches per variant after retrying safeguard refusals (10 per variant still refused). Same-claim pairs: 7723f1b 1, 3d538a0 2, all "Ian Fairbank" beside "Mr. Fairbank" in one puzzle; no hypothesis restating an answer in either. Misplaced `answers` edges 0 and 0; bare labels 0 and 0. Under 7723f1b no `candidate_solution` node and `answer_kind` on all 188 `answers` edges. Non-answer claims per patch 1.6 -> 0.7.
- [ ] 2 Package
- [ ] 3 Docs
- [ ] 4 Tests
- [ ] 5 Review

## Decisions

- Candidacy is an edge, not a field or a type: a field duplicates what the edge already says, and the edge already exists for every candidate.
- `answer_kind` on the edge: a kind describes how a claim answers a particular goal, and one claim may answer two goals.
- Id naming is mandatory: an id is unambiguous; text matching gave false matches and silently picks a node.
- The probe gates the merge, not the decision (council).

## Surprises

- 10 of 112 first patches leave out the goal node, taking it as made by `init`, and point `answers` edges at `G1` anyway. The probe judge now shows such a goal as implied.
- Under the new text the agent writes fewer non-answer hypotheses in its first patch (1.6 -> 0.7): observations link straight to the rival answers. Not a defect by itself; watch for lost step hypotheses in full runs.
