---
status: accepted
supersedes:
  - 0003-belief-sources.md
  - 0004-local-input-computed-belief-override.md
---

# Scores are a five-step scale with defaults

## Context

Claims carried a decimal `prior`, evidence edges a `likelihood` or `likelihood_ratio`, and every edge a required `reasoning` text. Three findings from the skill vs no-skill A/B and its follow-up runs (Sonnet 5, 22 True Detective items):

- The decimals claimed a calibration that does not exist. Belief separated right from wrong answers with an AUC of 0.41 and 0.55.
- Agents already wrote tiers. Across 262 recorded graphs, 93% of observation priors sat in 0.80–0.95, and edge ratios clustered on 1.2, 1.3, 1.5, 2 and 3.
- Most of the writing was boilerplate. `reasoning` was 45% of edge bytes, and graph writes cost $0.14 per run.

Scores still earn their place: a reader who sees a weak clue scored as a strong one can catch the mistake. The cost to cut is the writing, not the number.

## Decision

One optional integer `score`, 1 to 5, on claims and on evidence edges. The CLI maps it to a number through one table each.

| Score | Claim probability | `supports` ratio |
|---|---|---|
| 1 | 0.1 | 1.2 |
| 2 | 0.3 | 1.5 |
| 3 | 0.5 | 2 |
| 4 | 0.7 | 3 |
| 5 | 0.9 | 5 |

`contradicts` uses the reciprocal of the ratio.

Defaults, so that a score is written only for an exception:

| Object | Default |
|---|---|
| Observation | 5 |
| Hypothesis, candidate | 3 |
| Evidence edge | 3 |

- A claim's default applies only when it has no score and no belief-bearing `leads_to` premise. A premise-backed claim with no score inherits its premises' belief and adds nothing. Otherwise every step of a derivation would halve the belief.
- An explicit score on a premise-backed claim multiplies the inherited belief, as `prior` did.
- Every claim now has a belief source, so the rule that a claim requires one is gone. The stop gate that an answer must rest on observations stays.
- A correlation group is a list of edge ids and one required combined `score`. The edges share one type and one target. The score maps through the ratio table for evidence edges and through the probability table for `leads_to` premises. A grouped edge carries no score of its own.
- Edges take an optional `note` in place of the required `reasoning`. Nothing enforces a note. The skill asks for one when a score departs from its default or the link is not obvious.
- `prior`, `likelihood`, `likelihood_ratio`, edge `reasoning` and the old factor fields are rejected, not converted.

## Consequences

- An evidence edge with no score now moves belief, at ratio 2. Before, an edge without a likelihood had no numeric effect.
- Certainty cannot be written. The top score is 0.9.
- The scale cannot express a ratio above 5. Several independent clues still multiply.
- An enforced note was considered and rejected: it would push agents to leave scores at the default to avoid the writing.
- Old states fail validation. Benchmark states under `test-results/` stay as evidence and are not migrated.
