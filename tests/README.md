# Reasoning Graph Tests

Tests are split by role:

- `cli/` — executable CLI contract tests for `uv run rg ...` commands.
- `integration/` — broader driver, cost, audit, and invariant tests.
- `fixtures/` — reusable JSON states, patches, invalid cases, and golden outputs.
- `scenarios/` — human/eval prompt packets, blind problems, and spoiler validators.

## Fixtures

- `fixtures/valid/reasoning-graph-strict-good.json` — minimal strict-mode state that should validate/audit/stop-review.
- `fixtures/valid/` — durable valid state fixtures for schema/CLI regression tests.
- `fixtures/invalid/validate/` — states expected to fail `rg validate` with specific errors.
- `fixtures/invalid/audit/` — states expected to pass validation but fail `rg audit`.
- `fixtures/patches/` — expansion patch fixtures validated by schema and applied in round-trip tests.
- `fixtures/golden/` — deterministic CLI output snapshots for starter/review commands.

## Scenarios

Human/eval prompt packets live under `scenarios/`. Detailed scenario layout, prompt template, validator, and asset conventions live in `../docs/test-scenarios.md`.

## Run

```bash
uv run --group dev pytest tests/cli tests/integration -q
uv run rg validate tests/fixtures/valid/reasoning-graph-strict-good.json
uv run rg audit tests/fixtures/valid/reasoning-graph-strict-good.json
```

## Review notes

- Use validator files only after blind runs complete.
- Keep generated outputs separate from these inputs unless they are named clearly as run artifacts.
- A/B output artifacts live in `../test-results/`.
