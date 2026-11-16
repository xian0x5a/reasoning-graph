---
status: active
---

# Split `leads_to` into `premise_of` and `yields` (issue #7)

## Goal

Rename the claim use of `leads_to` to `premise_of`, and give the test-to-result link its own edge, `yields`. No alias: `leads_to` is rejected with a message naming both replacements.

## Intention

The name should say what the math does, because people read the graph too. `A leads_to T` reads as "A alone gets you to T", but one edge is one premise of T's argument: T stands or falls with all of them jointly. And `leads_to` also meant "this test produced this result", a provenance link with no belief, which the code told apart only by the source node's type.

The benchmark in the #7 comment found no change in how agents type edges (17/60 vs 25/60, p = 0.18). The owner chose the rename for precision for human readers; the agent-facing text must not get worse, so the endpoint checks below name the right edge when one is misused.

## Scope & Constraints

- Belief math unchanged: `premise_of` is the old claim `leads_to`; `yields` carries no belief, as a test never had any.
- Endpoints, enforced by validation:
  - `premise_of`: from observation, hypothesis, or candidate_solution, into hypothesis or candidate_solution.
  - `yields`: test -> observation only.
  - A misused endpoint names the edge meant: a test's result takes `yields`; a claim that calls for a test takes `prompts`; a conclusion drawn from observations is a hypothesis.
- No migration script and no alias (owner's legacy rule). Historical states under `test-results/` stay as records. An in-flight state fails `record`/`refresh` with one message per `leads_to` edge naming the replacement, so the agent can hand-edit and `refresh`.
- Historical records keep their wording: ADRs 0001-0016 and `plans/*.md` other than this one. ADR 0017 says how to read `leads_to` in them.
- Branch `feat/premise-of-and-yields`, one commit per layer.

## Work Plan

1. Code: models, schema enum and descriptions, validation (endpoint rules, removed-type message, `not_run` check on `yields`), costs (premise walk reads `premise_of` only), index/policy/case/page test-result lookups read `yields`, CSS selector. Rename in fixtures and tests. Suite green.
2. Docs: SKILL.md, skill docs, README, readme example patch (and screenshots if they show the name), ADR 0017.
3. Independent tests for the new contracts: removed-type message, endpoint rules, `not_run` with `yields`, belief unchanged across the rename.
4. Independent review; fix; final suite.

## Progress

- [x] Layer 1 code (08d8fd5): suite 458 passed. Tests that exercised now-invalid endpoints (a goal, constraint, or test as a premise; a premise into an observation) were removed or retargeted; a hypothesis as a test result now fails at record, so its fixture moved from invalid/audit to invalid/validate.
- [x] Layer 2 docs: skill text, docs, README, example patch, screenshots (only the edge chip changed), ADR 0017
- [x] Layer 3 independent tests: tests/cli/test_premise_of_and_yields.py (Sonnet, 29 cases), no code bugs found; suite 487 passed
- [ ] Layer 4 review

## Decisions

- One general message for a `leads_to` edge: a patch adds edges whose end nodes may not be in the patch, so the message cannot always tell which replacement applies.

## Surprises

- `mermaid` renders without validating, so a state with a premise_of from a goal into a scored node now raises the scored-deduction error there; before, a goal source did not count as a premise. Same behaviour as any scored deduced claim since ADR 0016, so left as is.
