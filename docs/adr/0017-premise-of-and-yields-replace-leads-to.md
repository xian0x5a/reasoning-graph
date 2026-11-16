---
status: accepted
amends:
  - 0005-node-types-name-observation-and-hypothesis-roles.md
  - 0009-scores-are-a-five-step-scale-with-defaults.md
  - 0014-a-ruled-out-claim-is-a-status-not-a-weight.md
  - 0016-a-deduced-claim-carries-no-score.md
---

# `premise_of` and `yields` replace `leads_to`

## Context

`leads_to` named two relations. From an observation or claim, it was a premise the target stands or falls with: the target's belief is the joint belief of all its premises (ADR 0016). From a test, it linked the observation that records the test's result, a link with no belief, since a test has none. The code told the two apart by the source node's type, and the validator accepted endpoints that meant nothing: benchmark states held `leads_to` edges into a test and between two observations.

The name also misread the math. `A leads_to T`, read one edge at a time, says A alone gets you to T, but one edge is one premise of T's argument, and no single premise settles T when there are several.

A benchmark before this change (issue #7) found no gain in how agents type edges from the rename: given the nodes of real graphs, Sonnet gave restating or eliminating hypotheses a premise edge 25 of 60 times with `leads_to` and 17 of 60 with `premise_of` (p = 0.18). The rename is for people reading the graph, the page, and the docs, who should see what the math does.

## Decision

- `premise_of`: the source is a premise the target stands or falls with. It runs from an observation, hypothesis, or candidate_solution into a hypothesis or candidate_solution. Belief is unchanged from the old claim `leads_to`.
- `yields`: a run test to the observation that records its result. It runs only from a test to an observation and moves no belief.
- Validation enforces both and names the edge meant when one is misused: a test's result takes `yields`, a claim that calls for a test takes `prompts`, a conclusion drawn from observations is a hypothesis.
- `leads_to` is rejected, with a message naming both replacements. No alias and no migration script.
- Earlier ADRs keep `leads_to` as written: read it as `premise_of`, or as `yields` when it runs from a test.

## Consequences

- A state written before this change fails `record`, `refresh`, and `audit` until each `leads_to` is retyped by hand. Benchmark states under `test-results/` stay as written, as records of their runs.
- A hypothesis recorded as a test's result now fails at `record`, not at `audit`.
- The code reads premises and test results by edge type instead of by the source node's type.
- The measured agent behaviour gives no reason to expect fewer edge mistakes, and maybe slightly fewer premise edges; the next benchmark should check.

## Considered

- Keep `leads_to` and only add the endpoint checks: most of the validation gain at no migration cost, and it scored higher on agent behaviour, but the name keeps misreading the math for people.
- Split off only `yields`: removes the double meaning, but keeps the misleading name on the belief edge.
- `deduces`: "O1 deduces H1" has the wrong subject, and a claim combining two parts is deduced by neither alone.
- Accept `leads_to` as an alias for a while: a compatibility path, and agents would keep writing the old name from old states.
