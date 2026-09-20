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

## Probability fixtures

Unresolved hypotheses use explicit priors; `0.5` denotes a deliberately neutral
starting belief. Observations and procedures carry reliability estimates.
Some synthetic premise-propagation fixtures use local `confidence: 1.0` on
derived nodes or candidates: these represent deterministic consequences of
their `leads_to` premises, so the premises supply the uncertainty. This is not
a default for unscored claims. Goals use `probability: 1.0` for acceptance of
the stated objective, not successful completion.
