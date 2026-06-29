# reasoning-graph package

Python library and `rg` CLI for the reasoning-graph skill.

## Install from Git

```bash
uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

Then run:

```bash
rg validate state.json
rg audit state.json
rg html state.json -o graph.html
```

If `rg --help` shows ripgrep instead of the reasoning-graph CLI, put the uv tool bin directory earlier on `PATH` or run the package through a project environment.

## Development

From the repository root:

```bash
uv --project packages/reasoning-graph run rg validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
```

Schemas are packaged under `src/reasoning_graph/schemas/`.
