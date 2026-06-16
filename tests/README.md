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

- `scenarios/prompts/no-skill-ab-prompt.md` — reusable A/B prompt for the normal/no-skill run.
- `scenarios/prompts/skill-ab-prompt.md` — reusable A/B prompt for the `reasoning-graph` skill run.
- `scenarios/countdown-island/` — countdown-island problem variants and spoiler validator.
- `scenarios/sea-shanty/` — Gold Bug DC33 / CryptoVillage 2025 Sea Shanty puzzle fixture and validator.
- `scenarios/theo-crypto-v2/` — text-only cold fixture for a two-line crypto challenge.
- `scenarios/reasoning-graph-hard-*.md` — hard detective-style packets and validators.
- `scenarios/reasoning-graph-sherlock-conan-*.md` — earlier blind observatory test and validator.
- `scenarios/locked-observatory-baseline-blind.md` — baseline prompt used for non-skill comparison.

## Run

```bash
uv run pytest tests/cli tests/integration -q
uv run rg validate tests/fixtures/valid/reasoning-graph-strict-good.json
uv run rg audit tests/fixtures/valid/reasoning-graph-strict-good.json
```

## Review notes

- Use validator files only after blind runs complete.
- Keep generated outputs separate from these inputs unless they are named clearly as run artifacts.
- A/B output artifacts live in `../test-results/`.
