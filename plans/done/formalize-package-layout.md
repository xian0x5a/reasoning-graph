# Formalize package layout

## Goal

Split the repository into a lightweight installable skill plus a standalone Python package.

Target layout:

```text
reasoning-graph/
├── skills/reasoning-graph/          # skill instructions and reference docs only
└── packages/reasoning-graph/        # Python library, CLI, schemas, tests
```

## Decisions

- Keep `skills/reasoning-graph/` copyable by skill installers that only copy the skill directory.
- Move the Python project to `packages/reasoning-graph/`.
- Put package tests under `packages/reasoning-graph/tests/`.
- Do not add a shim/wrapper under the skill directory.
- Skill docs must tell agents to install the CLI with `uv tool install` from the Git URL when the CLI is missing.
- Keep the current console script name `rg` for this migration; command rename is separate scope.

## Scope

In scope:

- Move package metadata, source, schemas, lock/workspace config, and tests.
- Update docs and tests for new paths and install model.
- Add a package README usable as Python package metadata.
- Update repository agent/test guidance for the new test location.
- Validate package import, CLI behavior, schema loading, and tests.

Out of scope:

- Adding skill-local shims.
- Publishing the package.
- Renaming the public CLI command.
- Preserving old path compatibility logic.

## Work Plan

1. Create `packages/reasoning-graph/`.
2. Move `skills/reasoning-graph/pyproject.toml`, `uv.lock`, and `src/` into the package area.
3. Move `tests/cli`, `tests/integration`, `tests/fixtures`, and `tests/README.md` under `packages/reasoning-graph/tests/`.
4. Change package metadata from `readme = "SKILL.md"` to package-local `README.md`.
5. Add or adjust root workspace config only if it reduces command friction without coupling installed skills to the repo checkout.
6. Update imports, schema paths, and subprocess helpers in tests.
7. Update `README.md`, `AGENTS.md`, `SKILL.md`, and skill docs to reflect:
   - package path: `packages/reasoning-graph/`
   - installed skill command: `rg ...`
   - missing CLI install command: `uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"`
8. Move pseudocode mirrors to the matching package path when they track source paths.
9. Run validation.

## Validation

From repo root, expected checks:

```bash
uv --project packages/reasoning-graph run python -m py_compile packages/reasoning-graph/src/reasoning_graph/*.py
uv --project packages/reasoning-graph run rg validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run rg audit packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
uv build packages/reasoning-graph --out-dir /tmp/reasoning-graph-dist
```

Add install smoke when local package is coherent:

```bash
uv tool install --force ./packages/reasoning-graph
rg validate packages/reasoning-graph/tests/fixtures/valid/minimal-state.json
```

## Risks

- `rg` may collide with ripgrep when globally installed. Docs should make command identity explicit.
- `npx skills` copied skill dir cannot rely on repo-local package paths.
- Schema loading depends on `reasoning_graph.schemas` package data; validate after build/install.
- Existing `.venv` may still point at the old editable source path; validation should use explicit `uv --project` commands.

## Progress

- 2026-06-29: Context fanout completed in `migration-context/`. Implementation handoff ready.
- 2026-06-29: Moved Python package metadata/source/schemas/lock to `packages/reasoning-graph/`.
- 2026-06-29: Moved package tests, fixtures, and scenarios to `packages/reasoning-graph/tests/` without moving cache directories.
- 2026-06-29: Updated package metadata to use package-local `README.md` and `testpaths = ["tests"]`.
- 2026-06-29: Updated root README, AGENTS.md, SKILL.md, skill docs, tests README, and source-mapped pseudocode paths.
- 2026-06-29: Added layout regression coverage in `packages/reasoning-graph/tests/cli/test_commands.py`.
- 2026-06-29: Validation passed: explicit package import, compile, `rg validate`, `rg audit`, `rg stop-review`, pytest, and `uv build`.
- 2026-06-29: Review fanout found no correctness blockers. Docs review requested install guidance in `docs/cost-model.md` and `docs/schema.md`; both were updated.
- 2026-06-29: Parent re-ran lock check, import, compile, `rg validate`, `rg audit`, `rg stop-review`, pytest, and `uv build`; all passed.
- 2026-06-29: Isolated `uv tool install --force ./packages/reasoning-graph` smoke passed using temporary `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`; installed `rg` validated the minimal fixture.
- 2026-06-29: Temporary orchestration outputs moved out of the repo to `~/.agents/artifacts/outputs/2026-06-29/formalize-package-layout/`.

## Outcomes

- Skill directory is docs/instructions only for tracked project files: `SKILL.md`, `docs/`, and `.dotman-skip`; no package source, project file, lockfile, or shim/bin remains there.
- Python package now builds from `packages/reasoning-graph/` and includes schemas as package data.
- Tests now run against explicit `uv --project packages/reasoning-graph` package paths, avoiding old editable-environment false passes.
- Skill docs now describe installed `rg` usage plus `uv tool install` from the package Git subdirectory when the CLI is missing or resolves to ripgrep.
