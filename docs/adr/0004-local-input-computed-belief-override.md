---
status: superseded
supersedes: 0001-score-names-encode-revisability.md
superseded_by: 0009-scores-are-a-five-step-scale-with-defaults.md
---

# Separate local input, computed belief, and explicit override

Superseded by [ADR 0009](0009-scores-are-a-five-step-scale-with-defaults.md) and [ADR 0010](0010-computed-belief-is-for-the-reader.md). The local input is now a `score` from 1 to 5 in place of `prior`. Computed belief stays output only and is shown in the renders. The `posterior` override is removed: no authored value overrules the graph's evidence.
