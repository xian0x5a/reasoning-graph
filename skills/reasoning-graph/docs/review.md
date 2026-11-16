# Pre-claim review

A second reader for the graph before an answer is claimed. The writer scores without seeing belief (`cost-model.md`); the reviewer sees belief and never edits. Belief only tells the reviewer where to look. Every finding is a fact about the evidence, so nothing the writer reads back is a number to aim at.

## Running it

1. Hand a read-only subagent the brief below, with the paths of `state.json` and `state.index.md`. The subagent renders the beliefs itself, so they never enter your context.
2. Read the findings. Apply the ones you accept in one patch, with a `note` on each edge or node you change.
3. Claim the answer and run `audit`. The answer gets one review: a re-review after edits would turn the reviewer's verdict into a threshold to tune against.

## Brief

```txt
You review a reasoning graph before its author claims an answer. Read only; edit nothing.
Run `reasoning-graph mermaid <state.json>`: each claim's label ends with its computed
belief. Also read <state.index.md> (every node and edge) and <state.json> (quotes, notes).

Use belief to find where to look, then judge each spot from the evidence itself:
1. Rivals both likely: two claims that cannot both be true are both above 50%.
2. Non-diagnostic support: a supports edge from an observation that a rival explains
   about as well, so it is about as expected if the target is false.
3. Shared cause: edges into one target from sources that share a source, an observation,
   a cause, or logical overlap, not grouped in one factor.
4. Wrong edge type: a claim that combines or restates other claims fed by supports from
   them; observations that each corroborate a claim on their own listed as leads_to premises.

Report one line per finding: the ids, the fact about the evidence, and the graph change
it implies (remove an edge, group edges, change an edge type).
Example: "O1 -> H1: O1 is equally expected under H2 (both predict a multi-chain drain);
remove the edge."
Write every finding as a fact about the evidence. Leave out beliefs, ranks, scores, and
how strong an edge should be: the author must not learn the numbers.
If nothing qualifies, say "no findings".
```

## Why it is shaped this way

- **Facts, not directions.** "O1 is equally expected under H2" survives the author not knowing any belief; "this edge is too strong" is a direction to tune toward.
- **One round, no gate.** `audit` never waits on a review, and the author is free to reject findings: in the project's reader evaluation, model readers caught every planted wrong weight, along with about four spurious findings per read.
- **Optional.** It costs one subagent run per answer, so it is for answers that matter and harnesses that have subagents.
