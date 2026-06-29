# AGENTS.md

## Scope

This repo contains the `reasoning-graph` skill and helper package.

## Layout

- Skill instructions and reference docs live under `skills/reasoning-graph/`.
- Python package source, schemas, CLI, and package tests live under `packages/reasoning-graph/`.
- Do not add skill-local shims, package source, `pyproject.toml`, or lockfiles under `skills/reasoning-graph/`.
- Installed skill usage expects the `rg` CLI from `uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"`; do not add a skill-local wrapper for it.

## Tests

- Put CLI command tests under `packages/reasoning-graph/tests/cli/` and broader driver/invariant tests under `packages/reasoning-graph/tests/integration/`.
- Keep reusable JSON fixtures under `packages/reasoning-graph/tests/fixtures/` when possible; keep human/eval prompt packets under `packages/reasoning-graph/tests/scenarios/`.
- Run package checks with `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`.
- Do not add generated reports, HTML, Mermaid, or benchmark outputs to git; keep those under ignored `test-results/` or `/tmp`.
