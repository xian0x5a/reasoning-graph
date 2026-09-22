---
status: accepted
supersedes: 0002-derived-node-has-no-local-score.md
---

# Claims require a belief source

## Context

PR #26 required local priors on candidates while forbidding inference confidence on derived nodes. That forced an extra factor onto candidates that only restated their premises, and made uncertain inference validity require another node. It also exposed a cost-engine bug: a zero cost from certain premises was mistaken for missing belief when likelihood evidence arrived. Support with ratio 2 could lower inherited certainty from 1.0 to 2/3.

A full revert would restore unscored standalone candidates priced as certain. Retaining the type-bound contract would preserve unnecessary authoring constraints. Neither addresses the intended distinction: absence of a belief source is different from a source whose probability is exactly 1.0.

## Decision

Keep the named score meanings from ADR 0001, but let evidence, assumptions, derived claims, and candidates use those fields according to what the number represents. Require every claim to have a local score, a belief source reachable through leads_to premises, or a calibrated joint-probability factor. Goals, constraints, and test procedures remain scoreless; their presence alone does not ground a claim. Likelihood updates are relative evidence, not a starting belief.

Track grounding independently of numeric truth cost and share that check between validation and scoring. Full-state validation rejects ungrounded claims. Direct cost consumers use a neutral 0.5 before likelihood updates for ungrounded claims rather than reporting certainty. A grounded zero cost remains actual certainty. Raw premise cycles remain invalid, including when factors or posteriors could hide them during evaluation.

Local inference confidence is optional. Use it only for additional inference reliability, or represent that uncertainty as a separate assumption when it deserves independent scrutiny. A candidate that restates an existing derivation inherits belief without another local factor. Posterior remains an explicit calibrated override, not a workaround for inheritance.

## Consequences

- Observation 0.8 times inference confidence 0.9 gives 0.72; an explicit validity assumption at 0.9 is an alternative, not another factor to add as well.
- A premise at 0.6 gives an unscored candidate belief 0.6. An additional local score is reserved for additional uncertainty.
- Certain premises remain certain under finite likelihood updates, including grouped premise and likelihood factors.
- Node schemas check field types and ranges; complete-state validation checks graph grounding after a patch is merged, including premises already in the state.
- Validation does not prove logical entailment or detect every form of double counting. Authors still justify omitted inference uncertainty and calibrate dependent evidence.

The operational contract and examples live in [the cost model](../../skills/reasoning-graph/docs/cost-model.md). Mandatory nonblank edge explanations and rendering improvements are retained; sentence count is guidance rather than a punctuation-based rejection rule.
