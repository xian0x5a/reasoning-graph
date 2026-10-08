# Reasoning Graph CLI Install

The skill docs are instructions only. Install the helper CLI separately when `reasoning-graph --help` is unavailable:

```bash
uv tool install "reasoning-graph @ git+https://github.com/xian0x5a/reasoning-graph.git#subdirectory=packages/reasoning-graph"
```

In a repository checkout, developers may run commands without tool install:

```bash
uv --project packages/reasoning-graph run reasoning-graph ...
```
