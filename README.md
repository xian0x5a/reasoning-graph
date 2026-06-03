# reasoning-graph

Reasoning-graph skill and helper tooling for graph-driven, auditable search over complex reasoning tasks.

Core files:

- `skills/reasoning-graph/SKILL.md` — agent-facing workflow and schema rules
- `skills/reasoning-graph/scripts/rg.py` — validator, UCS/frontier helper, audit, Mermaid/HTML renderer
- `tests/` — prompts, fixtures, and problem assets

Quick checks:

```bash
python -m py_compile skills/reasoning-graph/scripts/rg.py
python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json
python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json
```

Generate graph artifacts:

```bash
python skills/reasoning-graph/scripts/rg.py mermaid state.json > graph.mmd
python skills/reasoning-graph/scripts/rg.py html state.json -o graph.html
```

This repository intentionally ignores `test-results/` and generated `.html`/`.mmd` files.
