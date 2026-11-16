---
status: accepted
---

# Evidence goes on the claim it bears on

## Context

Belief flows one way, from sources to targets: evidence on a claim never reaches the premises it rests on (ADR 0009, ADR 0016). Issue #8 found that evidence on a claim can therefore lift it above a premise it cannot hold without: two score-5 clues on a claim put it at 95%, above its 90% premise.

Being above a premise is only wrong when the claim entails the premise: a restatement, or a combined claim above one of its parts. A claim a test result proves can rightly sit above the proof when independent clues support it, since a misread result leaves the claim unproven, not false.

After #6, agents stopped writing premises between claims, and the lift went with them: 0 of 14 runs against 9 of 42 before. What remained is one claim recorded as two nodes with its evidence split between them: a hypothesis that states what a candidate answers, often one hypothesis per suspect beside the candidates. In the true-detective benchmark it shows up in 2 of 14 runs after #6 and in 1 of 14 in each of two earlier arms, and the two nodes then disagree: "Narrator (Randy) did it" at 0.99 beside the candidate "Randy" at 0.67, "Lester is the robber" at 0.50 beside "Lester Barton" at 0.89. (The 9 of 14 runs in issue #7 count a wider class: restatements and eliminations typed `supports`.)

## Decision

- The math stays forward-only. Where evidence goes is the writer's call, guided by the skill:
  - one node per claim: a candidate states its claim, so evidence that it is the answer goes on it, and a rival answer is a rival candidate; a hypothesis feeding it states something else, a step, a motive, or how it was done, and evidence about that goes on the hypothesis;
  - a hypothesis that states a candidate's claim is merged into the candidate: its other edges move to the candidate, its reasons to the candidate's note, and it is removed;
  - evidence about a part of a combined claim goes on that part.
- The pre-claim reviewer flags one claim recorded twice.

## Consequences

- No check catches a restated claim: telling that two texts state one claim takes reading them. The reviewer brief covers it when a review runs.
- The rule sits where the agent picks alternatives, since that is where the duplicates start: in a probe of first record patches (14 puzzles, 4 samples each), a judge counting any hypothesis whose main claim is a candidate's, story attached or not, found one in 22 of 56 patches under the old text and 8 of 56 under this one; a stricter judge counting pure restatements found 7 and 2, and one hypothesis per suspect beside the candidates went from 3 patches to none. Stated only under one node per claim, the rule cut the first count to 13 but left the pure restatements (6) and the per-suspect hypotheses (3) in place.
- Evidence on a combined claim as a whole still lifts it above its parts. The skill says so, and puts evidence on the part it bears on.
- A claim proved by a test result may still sit above the proof.

## Considered

- Cap a claim at its weakest premise: one rule in code, but it blocks the proved claim with independent clues, and the evidence should have raised the premise too.
- Propagate evidence back to the premises: correct for every case, but it turns the forward cost walk into belief-network inference, and the scores are too coarse to make that precision worth it.
- Keep both nodes and make one the other's only premise, with all the evidence on that one, as the skill's "a claim that combines or restates others stands or falls with them" implied: beliefs agree, but the reader still sees one claim twice, and each later clue must go to the right one of the two. The skill now names only combining there.
- A `restates` edge whose two ends share their evidence: a new edge type and belief rule for what merging does with the existing ones. It needs the writer to spot the restatement just as merging does.
- Let `update_nodes` turn a hypothesis into a candidate: no run needed it, since the candidates existed from the first round.
