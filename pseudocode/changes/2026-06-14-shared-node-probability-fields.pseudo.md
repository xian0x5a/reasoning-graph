---
affects:
  - packages/reasoning-graph/src/reasoning_graph/render.py
---

# Shared Node Probability Fields

## Intent

Keep rendered node probability metadata aligned with the shared probability field definitions used by cost and validation code.

## Behavior

```pseudo
node detail rendering:
  read probability metadata keys from shared display-order field list
  preserve current display order: prior, confidence, probability, posterior
  render only keys present on the node
```
