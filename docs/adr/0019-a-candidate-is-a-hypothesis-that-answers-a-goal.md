---
status: accepted
amends:
  - 0005-node-types-name-observation-and-hypothesis-roles.md
  - 0018-evidence-goes-on-the-claim-it-bears-on.md
---

# A candidate is a hypothesis that answers a goal

## Context

The `candidate_solution` node type carried no math. A candidate shared its default score, its edges, and the belief walk with a hypothesis; it differed only in being the source of an `answers` edge and holding an `answer_kind`.

What the type did was split one claim in two. A writer recorded the answer as a label ("Randy") and the claim it reasoned about as a hypothesis ("Randy did it"), and the evidence divided between the two nodes (ADR 0018). It also broke one node per claim (ADR 0005): a hypothesis that turned out to settle a goal, such as a lemma that answers a sub-goal, had to be recreated as a candidate. Three of the five answer kinds (`method_hypothesis`, `clue_path`, `blocker`) name hypotheses.

## Decision

- Remove `candidate_solution`. A candidate is a `hypothesis` with an `answers` edge to the goal it would settle. The edge means: if this claim holds, the goal is settled. A step toward the answer answers a sub-goal it settles, or nothing.
- `answer_kind` moves onto the `answers` edge. It is required, has no default, and is checked against that edge's goal. A hypothesis that settles two goals gives each edge its own kind.
- ADR 0005's rule inverts: `answers` is the only edge from a hypothesis to a goal.
- A candidate's text states the whole claim ("Thornton killed Bryan"), not a label beside it.
- `summary.answer` names each answer by id. The exact-text match is removed: it matched "Thornton" inside "Sergeant Josiah Thornton", and "42" inside "142".
- ADR 0018 stands. Merging two nodes that state one claim may keep either, since neither has a type the other lacks.
- A state with a `candidate_solution` node, or an `answer_kind` on a node, fails validation with the replacement named. There is no migration.

## Consequences

- One rule decides candidacy, read from the edges; the page, the index, the answer checks, and the case all follow it. A hypothesis becomes a candidate by gaining an `answers` edge and stays the same node.
- A first-patch probe gated the change (14 puzzles, 4 samples each, 46 patches judged per version after safeguard refusals, one judge that sees answer claims by their `answers` edges, never node types). Against the ADR 0018 text, the new text gave:
  - same-claim pairs 1 against 2, all one puzzle that names a man twice as rival answers;
  - no hypothesis restating an answer in either version;
  - no `answers` edge on a claim that would not settle its goal in either version;
  - no `candidate_solution` node and `answer_kind` on all 188 `answers` edges.
  - First patches held fewer non-answer hypotheses (1.6 to 0.7 per patch): observations went straight to the rival answers.
- A step given an `answers` edge by mistake shows as a candidate on the page. No check fails on it unless it is named as the answer, so the guard is the skill's meaning of the edge.
- Old states are rewritten by hand or regenerated.

## Considered

- Keep the type and rely on the ADR 0018 text: the type keeps inviting a label beside a claim, and a lemma that settles a goal still has to be recreated.
- A `candidate` flag on the hypothesis: it repeats what the `answers` edge already says, and the two can disagree.
- `answer_kind` on the node: one claim that settles two goals in two ways has no place for its second kind.
- Keep the exact-text match as a fallback: it picks a node silently when the text appears inside another name.
- A council of three models (Opus, DeepSeek, Sonnet) reviewed the proposal over two rounds and adopted it with the changes above, at 0.75 to 0.8 confidence; the probe gates the merge, not the decision.
