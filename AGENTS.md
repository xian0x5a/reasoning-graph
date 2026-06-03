# AGENTS.md

## Scope

This repo contains the `reasoning-graph` skill and helper tooling.

## Tests

- Put tests for `skills/reasoning-graph/scripts/` code under `tests/scripts/`.
- Keep reusable JSON fixtures under `tests/fixtures/` when possible.
- Do not add generated reports, HTML, Mermaid, or benchmark outputs to git; keep those under ignored `test-results/` or `/tmp`.

## Validation

Before committing changes to `skills/reasoning-graph/scripts/rg.py`, run:

```bash
python -m py_compile skills/reasoning-graph/scripts/rg.py
python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json
python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json
```
