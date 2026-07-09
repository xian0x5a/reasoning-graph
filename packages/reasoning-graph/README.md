# reasoning-graph

Python library and CLI for building, validating, auditing, and rendering reasoning graphs.

## Install

```bash
uv tool install "reasoning-graph @ git+https://github.com/ewgdg/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

Then verify the CLI:

```bash
reasoning-graph --help
```

If the command is unavailable, ensure the uv tool bin directory is on `PATH`.

## Common commands

```bash
reasoning-graph validate state.json
reasoning-graph audit state.json
reasoning-graph html state.json -o graph.html
reasoning-graph schema state
reasoning-graph schema patch
```

## Development

Run from the repository root:

```bash
uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q
```

Schemas are packaged with the CLI and exposed through the `schema` command. Emitted schemas are standalone; the patch schema bundles the state definitions it references.
