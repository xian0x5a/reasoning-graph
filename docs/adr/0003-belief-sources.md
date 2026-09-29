---
status: superseded
supersedes: 0002-derived-node-has-no-local-score.md
superseded_by: 0009-scores-are-a-five-step-scale-with-defaults.md
---

# Claims require a belief source

Superseded by [ADR 0009](0009-scores-are-a-five-step-scale-with-defaults.md). Every claim now has a default score, so no claim lacks a belief source and the grounding check in validation is gone. Two rules carry over: a premise-backed claim with no score inherits belief without another local factor, and an answer must rest on observations before a `solved` stop.
