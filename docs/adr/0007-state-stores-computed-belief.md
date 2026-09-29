---
status: superseded
amends: 0004-local-input-computed-belief-override.md
superseded_by: 0010-computed-belief-is-for-the-reader.md
---

# The state stores computed belief on each claim

Superseded by [ADR 0010](0010-computed-belief-is-for-the-reader.md). Storing belief in the state let the agent tune scores toward a threshold, and belief did not track correctness. The state holds no computed belief; the renders compute it for the reader.
