---
status: accepted
amends:
  - 0009-scores-are-a-five-step-scale-with-defaults.md
---

# A deduced claim carries no score

## Context

`leads_to` and `supports` move belief in opposite ways: premises multiply, so each added one can only lower the target; evidence multiplies odds, so each added one raises it. The skill told the writing agent which to use through a list of cases (a claim that combines or restates others, a conclusion a result establishes, an elimination). Three reviews of that wording each found a case the list got wrong, such as a survivor of an elimination over an incomplete rival list shown at 90%.

The score on a claim also changed meaning when premises arrived. Without premises it is the claim's prior; with them, ADR 0009 multiplied it into the inherited belief as doubt about the step. A lemma scored 2 while open fell from 30% to 27% once a default observation proved it, unless the agent remembered to unset the score.

## Decision

- `leads_to` is a deduction. The skill states one question, once, under "Choosing the edge": if every source were certain, would the target be certain too? Yes: `leads_to`. No: evidence, scored by its likelihood ratio.
- A claim with a `leads_to` premise from an observation or claim, or a `leads_to` group, is deduced and carries no score. `record`, `refresh` and `audit` reject one, naming the claims and the two ways out: unset the score, or, if the step is not certain, link the sources by `supports` or add the doubt as a premise of its own (a hypothesis that the step holds). The error prints no belief, so ADR 0010 holds.
- A `leads_to` group keeps its score: it is the joint probability of its premises, not a score on the claim.

## Consequences

- A step's doubt is now a node the reader can see and a test can check, instead of a number folded into the claim. It computes the same: premise 0.7 and a validity premise at score 5 give 0.63, as the folded score did.
- States with a scored deduced claim fail validation until the score is unset; two test fixtures and several tests changed.
- The page shows no prior on a deduced claim.

## Considered

- Docs only, keeping the case list: each review round found another leak.
- Ignoring the score on a deduced claim: silent, and the card would still show it.
- Renaming `leads_to` to name the deduction (for example `premise_of`): stronger cue, but it touches every state and splits off the test-to-result use. Tracked as a separate issue.
