---
status: accepted
amends:
  - 0009-scores-are-a-five-step-scale-with-defaults.md
---

# A deduced claim carries no score

## Context

`leads_to` and `supports` move belief in opposite ways: premises multiply, so each added one can only lower the target; evidence multiplies odds, so each added one raises it. The skill told the writing agent which to use through a list of cases (a claim that combines or restates others, a conclusion a result establishes, an elimination). Three reviews of that wording each found a case the list got wrong, such as a survivor of an elimination over an incomplete rival list shown at 90%.

The score on a claim also changed meaning when premises arrived. Without premises it is the claim's prior; with them, ADR 0009 multiplied it into the inherited belief as doubt about the step. A lemma scored 2 while open fell from 30% to 27% once a default observation proved it, unless the agent remembered to unset the score.

A first replacement question, "if every source were certain, would the target be certain?", checked only that the premises suffice. Review found it let in a second proof as a premise (one proof 90%, two 81%) and sent a source the target needs but that does not settle it to `supports`, which lifted the target above it (59% against 46%).

## Decision

- A `leads_to` premise is a source the target stands or falls with: certain if all its premises hold, without a basis if any one fails. The skill states this once, under "Choosing the edge", with three outcomes:
  - stands and falls with them: `leads_to`;
  - falls with them but they would not make it certain: `leads_to`, plus what is missing as a premise of its own, a hypothesis (for an elimination, that the listed rivals are all there are);
  - survives losing one: that one is evidence, scored by its likelihood ratio.
- A claim with a `leads_to` premise from an observation or claim, or a `leads_to` group, carries no score. `record`, `refresh` and `audit` reject one, naming the claims and the ways out: unset it, add the missing premise, or link a source the target survives losing by `supports`. The error prints no belief, so ADR 0010 holds.
- A `leads_to` group keeps its score: it is the joint probability of its premises, not a score on the claim.

## Consequences

- Doubt about a step is now a node the reader can see and a test can check, instead of a number folded into the claim. It computes the same belief: premise 0.7 and a missing-piece premise at score 5 give 0.63, as the folded score did.
- The missing piece rests on its score alone until evidence supports it, so it does not ground an answer: an answer that needs it, with no evidence of its own, fails `audit`. The folded score never blocked the answer. This is intended: the assumption the answer rests on is now visible to the check.
- States with a scored deduced claim fail validation until the score is unset; two test fixtures and several tests changed.
- The page shows no prior on a deduced claim.

## Considered

- Docs only, keeping the case list: each review round found another leak.
- The sufficiency question with extra clauses for second proofs and needed-but-insufficient sources: back to a case list.
- Allowing the step-doubt score again, rejecting only when a scored claim first gains premises: fewer nodes and no `audit` friction, but `score` would again mean two things, and the check needs patch-level logic.
- Ignoring the score on a deduced claim: silent, and the card would still show it.
- Renaming `leads_to` to name the relation (for example `premise_of`): stronger cue, but it touches every state and splits off the test-to-result use. Tracked in issue #7.
