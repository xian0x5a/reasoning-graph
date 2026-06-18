# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs to compare hypotheses, track assumptions, keep alternatives alive, and produce an auditable answer. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

This repo is a Python project using `skills/reasoning-graph/src/reasoning_graph/`. Run the CLI with `uv run rg ...` so dependencies come from `uv.lock`. Agents should update relevant pseudocode before touching matching source code.

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
uv run rg template strict -o state.json
uv run rg init --goal "Diagnose outage" --strict -o state.json
cat > seed.json <<'JSON'
{
  "nodes": [
    {"id": "E1", "type": "evidence", "text": "Initial observed fact", "confidence": 0.9},
    {"id": "A1", "type": "assumption", "text": "Plausible cause to test", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Check the plausible cause", "status": "proposed"}
  ],
  "edges": [
    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 2.0},
    {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"}
  ],
  "frontier": [{"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.1}}]
}
JSON
uv run rg seed state.json --patch seed.json -i
uv run rg doctor state.json

# validate before driving search; audit after driver events exist
uv run rg validate state.json

# drive graph search
uv run rg frontier state.json
uv run rg next state.json --pop -i
cat > expansion.json <<'JSON'
{"no_new_work_reason": "Initial test queued; stop this smoke run before adding real follow-up branches."}
JSON
uv run rg expand state.json --item Q1 --patch expansion.json -i
uv run rg stop state.json --reason "Smoke run reached the first seeded test and stopped by user request" --outcome user_stopped -o state.stopped.json

# final review for a stopped driver state
uv run rg validate state.stopped.json
uv run rg audit state.stopped.json
uv run rg stop-review state.stopped.json

# render artifacts
uv run rg mermaid state.stopped.json > graph.mmd
uv run rg html state.stopped.json -o graph.html
```

`rg seed` is the safe first-use path from empty `init`/`template` states: it appends initial evidence/constraints/assumptions/tests plus root frontier items, validates the result, and leaves driver events empty so the first `next --pop` records the real `init`/`pop` events.

## Schemas

Machine-readable JSON Schemas live under `skills/reasoning-graph/src/reasoning_graph/schemas/`:

- `state.schema.json` for graph/search state files
- `patch.schema.json` for expansion patches

Schemas describe the modern interchange contract and explicitly reject known legacy aliases. `uv run rg validate` runs schema validation first, then semantic graph/policy validation that JSON Schema cannot express.

## Checks

```bash
uv run python -m py_compile skills/reasoning-graph/src/reasoning_graph/*.py
uv run rg validate tests/fixtures/valid/reasoning-graph-strict-good.json
uv run rg audit tests/fixtures/valid/reasoning-graph-strict-good.json
uv run --group dev pytest tests/cli tests/integration -q
```

Generated reports, Mermaid files, and benchmark outputs belong in `test-results/` or `/tmp`, not git.
