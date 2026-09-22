---
status: superseded
superseded_by: 0004-local-input-computed-belief-override.md
---

# Score names encode whether the value is expected to change

The confidence/prior distinction is superseded by [ADR 0004](0004-local-input-computed-belief-override.md). Both fields used the same local-probability calculation and neither was automatically rewritten. The current contract distinguishes local input (`prior`), computed output (`belief`), and explicit calibrated override (`posterior`), rather than naming two equivalent inputs as fixed and revisable.
