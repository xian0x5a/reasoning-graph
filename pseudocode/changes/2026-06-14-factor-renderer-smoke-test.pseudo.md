---
affects:
  - packages/reasoning-graph/tests/cli/test_commands.py
---

# Factor Renderer Smoke Test

## Intent

Verify virtual factor rendering emits Mermaid/HTML output that exposes factor nodes and grouped factor edges.

## Behavior

```pseudo
add renderer smoke test with a small graph containing a supports factor
run mermaid command on state
expect flowchart output to include the factor id and grouped supports/factor edge labels
run html command on same state
expect generated HTML to include the factor id and grouped supports/factor edge labels
```
