# reasoning-graph-skill

Reasoning-graph skill for graph-driven, auditable search over complex reasoning tasks.

Core files:

- `SKILL.md` — agent-facing workflow and schema rules
- `scripts/rg.py` — validator, UCS/frontier helper, audit, Mermaid/HTML renderer
- `tests/` — prompts, fixtures, and problem assets

Quick checks:

```bash
python -m py_compile scripts/rg.py
python scripts/rg.py validate tests/reasoning-graph-strict-good.json
python scripts/rg.py audit tests/reasoning-graph-strict-good.json
```

Generate graph artifacts:

```bash
python scripts/rg.py mermaid state.json > graph.mmd
python scripts/rg.py html state.json -o graph.html
```

This repository intentionally ignores `test-results/` and generated `.html`/`.mmd` files.
