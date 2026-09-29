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

Claims and evidence edges take one optional `score` from 1 to 5. Belief is
computed from the graph when it is rendered and is never stored. Goal,
constraint, and test nodes carry no score. The removed `prior`, `confidence`,
`probability`, `posterior`, `likelihood`, `likelihood_ratio`, and `belief`
fields appear only in rejection tests.

A claim without a score takes its type default unless claim premises give it a
belief; fixtures write a score only where the default is wrong. Tests cover the
defaults, the two score tables, recalculation without writeback, and atomic
rejection of invalid inputs.
