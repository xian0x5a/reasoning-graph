# reasoning-graph

An agent skill for solving messy reasoning tasks with an explicit graph instead of a hidden linear chain.

Use it when an agent needs durable working memory for a long task, an evidence-grounded answer, and a reviewable record of how it got there. Useful for puzzles, root-cause analysis, ambiguous debugging, and planning under uncertainty.

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

## How it works

The graph is the agent's working memory and the gate on its final answer, not a scheduler:

1. `init` frames the goal.
2. The agent works the problem its own way and `record`s what each step produced: observations (with `source` and verbatim `quote`), hypotheses, tests and their results, candidate answers. Every `record` refreshes `state.html` so a human can follow along.
3. Belief is computed from the graph: observation priors, `leads_to` premises, and likelihood updates.
4. `stop` accepts a `solved` answer only when it is grounded in observations, every test has a recorded result, and the reported answer names the graph's best candidate.

## Helper commands

File-input mutating commands rewrite the input state by default; use `-o <path>` for a separate file or `-o -` for stdout.

```bash
rg="uv --project packages/reasoning-graph run reasoning-graph"

$rg init --goal "Diagnose outage" --strict -o state.json
cat > step.json <<'JSON'
{
  "reason": "Read the maintenance log",
  "nodes": [
    {"id": "O1", "type": "observation", "text": "Pump P2 restarted twice before the outage", "source": "maintenance.log line 40", "quote": "P2 restarted 02:10, 02:14", "prior": 0.95},
    {"id": "T1", "type": "test", "text": "Compare the outage start with the restart times"}
  ],
  "edges": [
    {"id": "O1-T1", "from": "O1", "to": "T1", "type": "prompts", "reasoning": "Restarts just before an outage suggest a timing check."}
  ]
}
JSON
$rg record state.json --patch step.json      # appends a record event, refreshes state.html
$rg beliefs state.json                        # computed belief per claim
$rg doctor state.json

$rg stop state.json --reason "Smoke run stopped by user request" --outcome user_stopped -o state.stopped.json

# final checks on the stopped state
$rg validate state.stopped.json
$rg audit state.stopped.json

# render artifacts
$rg mermaid state.stopped.json > graph.mmd
$rg html state.stopped.json -o graph.html
```

A `solved` stop needs every test to have a result `observation` linked by `leads_to`; record a failed or skipped check as a result too.

## Schemas

Machine-readable JSON Schemas are packaged with the CLI. Print them from any install:

```bash
reasoning-graph schema state
reasoning-graph schema patch
```

In this repository, source schemas live under `packages/reasoning-graph/src/reasoning_graph/schemas/`:

- `state.schema.json` for graph state files
- `patch.schema.json` for `record` patches

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
