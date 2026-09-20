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

Node scores follow the type contract: hypotheses use `prior` or `posterior`,
evidence uses `confidence`, derived nodes take their belief from `leads_to`
premises, and goal, constraint, and test nodes carry no score.

Unresolved hypotheses use an explicit prior; `0.5` denotes a deliberately
neutral starting belief, and `1.0` means certainty, never an unknown or
unspecified score. Synthetic premise-propagation fixtures give a restating
candidate `prior: 1.0` so that its `leads_to` premises supply all the
uncertainty.
