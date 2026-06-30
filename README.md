# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs to compare hypotheses, track assumptions, keep alternatives alive, and produce an auditable answer. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

## Repository layout

```text
skills/reasoning-graph/          # installable skill instructions and reference docs
packages/reasoning-graph/        # Python library, `reasoning-graph` CLI, schemas, and package tests
tests/scenarios/                 # repository-level human/eval prompt packets
```

The skill directory is docs/instructions only. The Python project lives under `packages/reasoning-graph/`, with source under `packages/reasoning-graph/src/reasoning_graph/`.

Installed-skill users should install the CLI when `reasoning-graph` is missing:

```bash
uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

Development commands should be explicit from the repo root:

```bash
uv --project packages/reasoning-graph run reasoning-graph validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
```

Agents should update relevant pseudocode before touching matching source code.

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
uv --project packages/reasoning-graph run reasoning-graph init --goal "Diagnose outage" --strict -o state.json
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
uv --project packages/reasoning-graph run reasoning-graph seed state.json --patch seed.json -i
uv --project packages/reasoning-graph run reasoning-graph doctor state.json

# validate before driving search; audit after driver events exist
uv --project packages/reasoning-graph run reasoning-graph validate state.json

# drive graph search
uv --project packages/reasoning-graph run reasoning-graph frontier state.json
uv --project packages/reasoning-graph run reasoning-graph next state.json --pop -i
cat > expansion.json <<'JSON'
{"no_new_work_reason": "Initial test queued; stop this smoke run before adding real follow-up branches."}
JSON
uv --project packages/reasoning-graph run reasoning-graph expand state.json --item Q1 --patch expansion.json -i
uv --project packages/reasoning-graph run reasoning-graph stop state.json --reason "Smoke run reached the first seeded test and stopped by user request" --outcome user_stopped -o state.stopped.json

# final review for a stopped driver state
uv --project packages/reasoning-graph run reasoning-graph validate state.stopped.json
uv --project packages/reasoning-graph run reasoning-graph audit state.stopped.json
uv --project packages/reasoning-graph run reasoning-graph stop-review state.stopped.json

# render artifacts
uv --project packages/reasoning-graph run reasoning-graph mermaid state.stopped.json > graph.mmd
uv --project packages/reasoning-graph run reasoning-graph html state.stopped.json -o graph.html
```

`reasoning-graph seed` appends evidence/constraints/assumptions/tests plus root frontier items. Before the first driver event it leaves events empty so `next --pop` records the real `init`/`pop` events; after driver init it records a `seed` event and requires patch `reason` for provenance.

## Schemas

Machine-readable JSON Schemas live under `packages/reasoning-graph/src/reasoning_graph/schemas/`:

- `state.schema.json` for graph/search state files
- `patch.schema.json` for expansion patches

Schemas describe the modern interchange contract and explicitly reject known legacy aliases. `reasoning-graph validate` runs schema validation first, then semantic graph/policy validation that JSON Schema cannot express.

## Checks

```bash
uv --project packages/reasoning-graph run python -m py_compile packages/reasoning-graph/src/reasoning_graph/*.py
uv --project packages/reasoning-graph run reasoning-graph validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run reasoning-graph audit packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
uv build packages/reasoning-graph --out-dir /tmp/reasoning-graph-dist
```

Generated reports, Mermaid files, and benchmark outputs belong in `test-results/` or `/tmp`, not git.
