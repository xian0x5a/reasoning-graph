# reasoning-graph package

Python library and `reasoning-graph` CLI for the reasoning-graph skill.

## Install from Git

```bash
uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

Then run:

```bash
reasoning-graph validate state.json
reasoning-graph audit state.json
reasoning-graph html state.json -o graph.html
```

If `reasoning-graph --help` is unavailable, ensure the uv tool bin directory is on `PATH` or run the package through a project environment.

## Development

From the repository root:

```bash
uv --project packages/reasoning-graph run reasoning-graph validate packages/reasoning-graph/tests/fixtures/valid/reasoning-graph-strict-good.json
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
```

Schemas are packaged under `src/reasoning_graph/schemas/` and can be printed from an install:

```bash
reasoning-graph schema state
reasoning-graph schema patch
```
