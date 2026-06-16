# AGENTS.md

## Scope

This repo contains the `reasoning-graph` skill and helper tooling.

## Tests

- Put CLI command tests under `tests/cli/` and broader driver/invariant tests under `tests/integration/`.
- Keep reusable JSON fixtures under `tests/fixtures/` when possible; keep human/eval prompt packets under `tests/scenarios/`.
- Do not add generated reports, HTML, Mermaid, or benchmark outputs to git; keep those under ignored `test-results/` or `/tmp`.
