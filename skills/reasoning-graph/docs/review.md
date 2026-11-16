# Pre-claim review

A second reader for the graph before an answer is claimed. The writer scores without seeing belief (`cost-model.md`); the reviewer sees belief and never edits. Belief only tells the reviewer where to look. Every finding is a fact about the evidence, so nothing the writer reads back is a number to aim at.

## Running it

1. Hand a read-only subagent the brief below, with the paths of `state.json` and `state.index.md`. The subagent renders the beliefs itself, so they never enter your context.
2. Read the findings. Apply the ones you accept in one patch, with a `note` on each edge or node you change.
3. Claim the answer and run `audit`. The answer gets one review: a re-review after edits would turn the reviewer's verdict into a threshold to tune against.

## Brief

```txt
You review a reasoning graph before its author claims an answer. Read only; edit nothing.
Run `reasoning-graph mermaid <state.json>`: each claim's label shows its computed
belief. Also read <state.index.md> (every node and edge) and <state.json> (quotes, notes).

Use belief to find where to look, then judge each spot from the evidence itself:
1. Rivals both likely: two claims that cannot both be true both look likely. Report what
   lifts them (items 2-4), that they belong in one exclusive set, or that no recorded
   evidence separates them (add a test); the fact that both are likely is a belief, not
   a finding.
2. Non-diagnostic evidence: a supports or contradicts edge from an observation about as
   expected whether its target is true or false, because every rival explains it as well.
3. Shared cause: edges into one target from sources that share a source, an observation,
   a cause, or logical overlap, not grouped in one factor.
4. Wrong edge type. A premise (`premise_of`) is a source its target stands or falls with:
   certain if all its premises hold, without a basis if any one fails. Flag a premise
   the target would survive losing because another source still settles it (a second
   proof, one of several alternatives), or that only corroborates it (a clue); premises
   that would not make the target certain, with no premise for what is missing (an
   elimination over a rival list that may be incomplete); and a supports from a source
   the target cannot hold without (a part of a combined claim).
5. Rejected but standing: a claim that an observation settles as false (a user's rejection,
   a failed check it cannot survive) held down only by a contradicts edge.
6. Overreach: a rules_out edge from an observation that does not settle its claim as false.

Report one line per finding: the ids, the fact about the evidence, and the graph change
it implies (remove an edge, group edges, change an edge type, rule a claim out, add an
exclusive set, add a test).
Example: "O1 -> H1: every rival (H2, H3, H4) predicts a multi-chain drain as well as H1
does, so O1 is as expected if H1 is false; remove the edge."
Write every finding as a fact about the evidence. Leave out beliefs, ranks, scores, and
how strong an edge should be: the author must not learn the numbers.
If nothing qualifies, say "no findings".
```

## Why it is shaped this way

- **Facts, not directions.** "O1 is as expected under every rival" survives the author not knowing any belief; "this edge is too strong" is a direction to tune toward.
- **One round, no gate.** `audit` never waits on a review, and the author is free to reject findings: in the project's reader evaluation, model readers caught every planted wrong weight, along with about four spurious findings per read.
- **Optional.** It costs one subagent run per answer, so it is for answers that matter and harnesses that have subagents.
