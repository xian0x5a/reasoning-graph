# AGENTS.md

## Scope

This repo contains the `reasoning-graph` skill and helper tooling.

## Tests

- Put tests for `scripts/` code under `tests/scripts/`.
- Keep reusable JSON fixtures under `tests/fixtures/` when possible.
- Do not add generated reports, HTML, Mermaid, or benchmark outputs to git; keep those under ignored `test-results/` or `/tmp`.

## Validation

Before committing changes to `scripts/rg.py`, run:

```bash
python -m py_compile scripts/rg.py
python scripts/rg.py validate tests/reasoning-graph-strict-good.json
python scripts/rg.py audit tests/reasoning-graph-strict-good.json
```
