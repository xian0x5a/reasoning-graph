---
status: accepted
amends:
  - 0009-scores-are-a-five-step-scale-with-defaults.md
---

# A ruled-out claim is a status, not a weight

## Context

ADR 0009 caps evidence at a ratio of 5 and gives the scale no impossibility. The rejection flow recorded a user's rejection as a score 5 `contradicts` edge, worth ÷5. A rejected answer is usually the claim with the strongest case in the graph, so ÷5 barely moved it:

- In a recorded loop run (`the-anonymous-bank-robber`, `s55-loop-r2`, round 3) three rejected candidates rendered at 95%, 97% and 92%.
- Replays of the recorded loop runs found 39 of 77 user-rejected candidates still at 50% or more.
- A steeper contradiction alone did not fix it. At ÷20, 12 of 77 stayed at 50% or more, most of them carried by a strong `leads_to` premise that the rejection does not touch. Stacked support beats any finite ratio.

The docs also disagreed: score 5 was labelled "decisive", `contradicts` "does not disqualify the target by itself", and a ruled-out claim was to be recorded "in its text", which the skill forbids elsewhere.

## Decision

- A `rules_out` edge runs from an observation to a hypothesis or candidate. It takes no score and cannot be grouped.
- The belief walk caps its target at `0.001`, rendered `<1%`, after premises and evidence. Claims that take the target as a premise inherit the cap.
- The rejection flow uses `rules_out`; `contradicts` stays for doubt.
- The evidence scale is unchanged: score 5 now reads "very strong, never proof", and the ratio stays 5.
- `audit` does not check it. ADR 0010 keeps belief out of every gate.

## Consequences

- A rejected answer reads `<1%`, and the page names the observation that ruled it out.
- A wrong rule-out sinks a true claim, and no evidence lifts it back. The guards: only an observation can rule out, the page shows which one and its quote, and changing the edge to `contradicts` undoes it, since no belief is stored.

## Considered

- ÷20 for score 5 `contradicts` only: still loses to stacked support and to premises (above).
- ×20 and ÷20 for both edge types: one over-scored support takes a default hypothesis to 95%.
- Any score 5 `contradicts` vetoes its target: a cliff on the least calibrated step, and score 5 is the most common explicit contradiction score.
- A page mark beside an unchanged belief: kept as a separate aid, but alone it leaves "97%" on a rejected answer.
