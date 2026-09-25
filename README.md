# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs to compare hypotheses, keep alternatives alive, and produce an auditable answer. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

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

## Algorithm

The skill treats reasoning as heuristic best-first search over a graph:

1. Extract goal, facts, constraints.
2. Add hypotheses/tests as frontier items.
3. Score each item by truth cost, verification cost, effort budget, reasoning complexity, constraint tension, contradiction penalties, and optional estimated remaining work.
4. Pop lowest `search_cost`; expand into observations, tests, child branches, or candidate answers.
5. Update costs as observations arrive; keep branches visible instead of deleting them.
6. Stop only when frontier is exhausted, confidence/quantity threshold is met, budget is spent, or a real blocker is proved.

## Helper commands

File-input mutating commands rewrite the input state by default; use `-o <path>` for a separate file or `-o -` for stdout.

```bash
# bootstrap and inspect state
uv --project packages/reasoning-graph run reasoning-graph init --goal "Diagnose outage" --strict -o state.json
cat > seed.json <<'JSON'
{
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Initial observed fact", "prior": 0.9},
    {"id": "H1", "type": "hypothesis", "text": "Plausible cause to test", "prior": 0.4},
    {"id": "T1", "type": "test", "text": "Check the plausible cause"}
  ],
  "edges": [
    {"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", "likelihood_ratio": 2.0, "reasoning": "The observed signal is more likely when the target claim is true."},
    {"id": "H1-T1", "from": "H1", "to": "T1", "type": "prompts", "reasoning": "This claim motivates the follow-up check."}
  ],
  "frontier": [{"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.1}}]
}
JSON
uv --project packages/reasoning-graph run reasoning-graph seed state.json --patch seed.json
uv --project packages/reasoning-graph run reasoning-graph doctor state.json

# validate before driving search; audit after driver events exist
uv --project packages/reasoning-graph run reasoning-graph validate state.json

# drive graph search
uv --project packages/reasoning-graph run reasoning-graph frontier state.json
uv --project packages/reasoning-graph run reasoning-graph next state.json --pop
cat > expansion.json <<'JSON'
{
  "nodes": [{"id": "O2", "type": "observation", "text": "Check ran; the plausible cause was not confirmed in this smoke run", "prior": 0.9}],
  "edges": [{"id": "T1-O2", "from": "T1", "to": "O2", "type": "leads_to", "reasoning": "The check produced this observation."}],
  "no_new_work_reason": "Smoke run; stop before adding real follow-up branches."
}
JSON
uv --project packages/reasoning-graph run reasoning-graph expand state.json --item Q1 --patch expansion.json
uv --project packages/reasoning-graph run reasoning-graph stop state.json --reason "Smoke run reached the first seeded test and stopped by user request" --outcome user_stopped -o state.stopped.json

# final review for a stopped driver state
uv --project packages/reasoning-graph run reasoning-graph validate state.stopped.json
uv --project packages/reasoning-graph run reasoning-graph audit state.stopped.json
uv --project packages/reasoning-graph run reasoning-graph stop-review state.stopped.json

# render artifacts
uv --project packages/reasoning-graph run reasoning-graph mermaid state.stopped.json > graph.mmd
uv --project packages/reasoning-graph run reasoning-graph html state.stopped.json -o graph.html
```

Under the strict profile, expanding a `test` item must record its result as an `observation` linked by `leads_to`, and an expansion that adds no frontier work must say why (`no_new_work_reason`); `expand` rejects the patch otherwise.

`reasoning-graph seed` appends observations/constraints/hypotheses/tests plus root frontier items. Before the first driver event it leaves events empty so `next --pop` records the real `init`/`pop` events; after driver init it records a `seed` event and requires patch `reason` for provenance.

## Schemas

Machine-readable JSON Schemas are packaged with the CLI. Print them from any install:

```bash
reasoning-graph schema state
reasoning-graph schema patch
```

In this repository, source schemas live under `packages/reasoning-graph/src/reasoning_graph/schemas/`:

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
