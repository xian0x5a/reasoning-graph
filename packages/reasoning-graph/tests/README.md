# reasoning-graph tests

- `cli/` — executable CLI contract tests for `uv --project packages/reasoning-graph run rg ...`.
- `integration/` — broader driver, cost, and invariant tests.
- `fixtures/` — reusable JSON states, patches, and golden outputs.
- Root `tests/scenarios/` — human/eval prompt packets for skill evaluation, not package tests.

Installed skill users should install the CLI with `uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"`; package tests use the explicit project commands below so they do not depend on ambient PATH state.

From the repository root:

```bash
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
uv --project packages/reasoning-graph run rg validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run rg audit packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
```
