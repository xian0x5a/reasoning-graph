# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs to compare hypotheses, track assumptions, keep alternatives alive, and produce an auditable answer. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

This repo is a Python project using `skills/reasoning-graph/src/reasoning_graph/`. The skill keeps `skills/reasoning-graph/scripts/rg.py` as a compatibility wrapper. Agents should update relevant pseudocode before touching matching source code.

## Algorithm

The skill treats reasoning as heuristic uniform-cost search over a graph:

1. Extract goal, facts, constraints.
2. Add assumptions/tests as frontier items.
3. Score each item by truth cost, verification cost, effort budget, reasoning complexity, constraint tension, evidence penalties, and optional estimated remaining work.
4. Pop lowest `search_cost`; expand into evidence, tests, child branches, or candidate answers.
5. Update costs as evidence arrives; keep branches visible instead of deleting them.
6. Stop only when frontier is exhausted, confidence/quantity threshold is met, budget is spent, or a real blocker is proved.

## Helper commands

```bash
# bootstrap and inspect state
python skills/reasoning-graph/scripts/rg.py template strict -o state.json
python skills/reasoning-graph/scripts/rg.py init --goal "Diagnose outage" --strict -o state.json
python skills/reasoning-graph/scripts/rg.py doctor state.json
python skills/reasoning-graph/scripts/rg.py stop-review state.json --draft answer.md

# validate and audit a graph state
uv run rg validate state.json
uv run rg audit state.json
# compatibility wrapper still works:
python skills/reasoning-graph/scripts/rg.py validate state.json

# drive graph search
python skills/reasoning-graph/scripts/rg.py frontier state.json
python skills/reasoning-graph/scripts/rg.py next state.json --pop -i
python skills/reasoning-graph/scripts/rg.py expand state.json --item Q1 --patch expansion.json -i
python skills/reasoning-graph/scripts/rg.py stop state.json --reason "best candidate verified" --outcome solved -i

# render artifacts
python skills/reasoning-graph/scripts/rg.py mermaid state.json > graph.mmd
python skills/reasoning-graph/scripts/rg.py html state.json -o graph.html
```

## Schemas

Machine-readable JSON Schemas live under `skills/reasoning-graph/src/reasoning_graph/schemas/`:

- `state.schema.json` for graph/search state files
- `patch.schema.json` for expansion patches

Schemas describe the modern interchange contract and explicitly reject known legacy aliases. `rg.py validate` runs schema validation first, then semantic graph/policy validation that JSON Schema cannot express.

## Checks

```bash
uv run python -m py_compile skills/reasoning-graph/scripts/rg.py skills/reasoning-graph/src/reasoning_graph/*.py
uv run rg validate tests/reasoning-graph-strict-good.json
uv run rg audit tests/reasoning-graph-strict-good.json
uv run python -m unittest discover -s tests/scripts
```

Generated reports, Mermaid files, and benchmark outputs belong in `test-results/` or `/tmp`, not git.
