# reasoning-graph tests

- `cli/` — executable CLI contract tests for `uv --project packages/reasoning-graph run reasoning-graph ...`.
- `integration/` — broader driver, cost, and invariant tests.
- `fixtures/` — reusable JSON states, patches, and golden outputs.
- Root `tests/scenarios/` — human/eval prompt packets for skill evaluation, not package tests.

Installed skill users should install the CLI with `uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"`; package tests use the explicit project commands below so they do not depend on ambient PATH state.

From the repository root:

```bash
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
uv --project packages/reasoning-graph run reasoning-graph validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run reasoning-graph audit packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
```

## Score fixtures

Claims use an optional local `prior` and may supply a calibrated `posterior`
override. Effective `belief` is computed from the graph, not stored on nodes.
Goal, constraint, and test nodes carry no score. Removed `confidence` and
`probability` fields, and authored node `belief`, appear only in rejection tests.

Standalone claims require a prior or posterior; premise-backed claims may
inherit belief without another local factor. `0.5` denotes a deliberately
neutral prior, and `1.0` means certainty, never an unknown score. Tests cover
inherited certainty, local inference priors, recalculation without writeback,
explicit overrides, and atomic rejection of invalid inputs.
