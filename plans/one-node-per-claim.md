---
status: active
---

# One node per claim: evidence on the claim it bears on (issue #8)

## Goal

Stop one claim being recorded as two nodes with its evidence split between them, the shape that remains of #8 after #6 and #7. Keep the belief math as it is.

## Intention

Belief flows one way, from sources to targets: evidence on a claim never reaches its premises. So where a writer puts evidence decides whether two nodes that must agree do agree. In the September and post-#6 benchmark runs, a hypothesis restating a candidate ("Thornton is the killer" beside the candidate "Sergeant Josiah Thornton") shows up in about 2 of 14 runs per arm, with the two at 0.89 and 0.82, 0.99 and 0.67, or 0.50 and 0.89. A reader sees one claim at two beliefs.

No mechanical check can tell that two texts state one claim, and a cap on a claim at its weakest premise would block a correct case (a claim a test result proves, with independent clues, may rightly sit above the proof). So the fix is in what the writer is told and what the reviewer looks for.

## Scope & Constraints

- Skill text only, plus an ADR; no change to code, schema, or math.
- SKILL.md: one node per claim covers a candidate and a hypothesis that restates it: merge the hypothesis into the candidate; evidence goes on the claim it bears on.
- docs/review.md: the reviewer flags one claim recorded twice.
- cost-model.md: say that belief flows forward only, and what follows for where evidence goes.
- ADR 0018 records the decision and the rejected options (cap, back-propagation, a `restates` edge, retyping a hypothesis into a candidate).
- Agent-facing wording follows the writing-for-agents rules: positive target, one source of truth per meaning.

## Work Plan

1. Skill text, review brief, cost-model, ADR 0018. Suite green (docs are not tested, but README image paths and fixtures must not break).
2. Probe: give Sonnet the problem of each true-detective item run after #6 and ask for its first record patch, under main's SKILL.md and the branch's, 4 samples each; a blind Opus judge, seeing only the goal, candidates, and hypotheses, names every hypothesis that restates a candidate. Evidence under `~/.agents/artifacts/outputs/reasoning-graph/2026-11-16/one-node-per-claim/`.
3. Independent review of the wording; fix; commit.

## Progress

- [x] Layer 1 text, revised after an Opus wording review: one rule (merge into the candidate) instead of three directions for the evidence; evidence about a step goes on the step; ADR 0018 lists keeping both nodes as a considered option
- [ ] Layer 2 probe
- [ ] Layer 3 review

## Decisions

- Skill text over code (matrix in the #8 handoff): docs 4.0, back-propagation 3.45, cap 3.4, `restates` edge 2.85, on belief correctness 35%, simplicity 25%, agent compliance 25%, reader clarity 15%.
- No type change from hypothesis to candidate: in every post-#6 run the candidates exist from round 1, so the duplicate is not a hypothesis that later became the answer.

## Surprises

- Sonnet's safeguards flagged one detective-puzzle prompt as unsafe; the probe retries and skips a job that keeps failing, for both variants alike.
