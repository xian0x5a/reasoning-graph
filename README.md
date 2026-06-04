# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs to compare hypotheses, track assumptions, keep alternatives alive, and produce an auditable answer. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

## Algorithm

The skill treats reasoning as heuristic uniform-cost search over a graph:

1. Extract goal, facts, constraints.
2. Add assumptions/tests as frontier items.
3. Score each item by truth cost, verification cost, effort budget, reasoning complexity, constraint tension, and evidence penalties.
4. Pop lowest `search_cost`; expand into evidence, tests, child branches, or candidate answers.
5. Update costs as evidence arrives; keep branches visible instead of deleting them.
6. Stop only when frontier is exhausted, confidence/quantity threshold is met, budget is spent, or a real blocker is proved.

## Helper commands

```bash
# validate and audit a graph state
python skills/reasoning-graph/scripts/rg.py validate state.json
python skills/reasoning-graph/scripts/rg.py audit state.json

# drive graph search
python skills/reasoning-graph/scripts/rg.py frontier state.json
python skills/reasoning-graph/scripts/rg.py next state.json --pop -i
python skills/reasoning-graph/scripts/rg.py expand state.json --item Q1 --patch expansion.json -i
python skills/reasoning-graph/scripts/rg.py stop state.json --reason "best candidate verified" --outcome solved -i

# render artifacts
python skills/reasoning-graph/scripts/rg.py mermaid state.json > graph.mmd
python skills/reasoning-graph/scripts/rg.py html state.json -o graph.html
```

## Checks

```bash
python -m py_compile skills/reasoning-graph/scripts/rg.py skills/reasoning-graph/scripts/reasoning_graph/*.py
python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json
python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json
python -m unittest discover -s tests/scripts
```

Generated reports, Mermaid files, and benchmark outputs belong in `test-results/` or `/tmp`, not git.
