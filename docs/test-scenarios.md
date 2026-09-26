# Test scenario format

Human/eval scenarios live under `tests/scenarios/`. Keep every scenario in its own slug directory; no loose scenario Markdown files at the root.

## Directory layout

```text
tests/scenarios/
  _templates/
    no-skill.md
    reasoning-graph.md
  <scenario-slug>/
    problem.md
    problem.v2.md              # optional harder/revised variants, same validator unless noted
    problem.v3.md
    validator.md                # optional, spoiler-only
    assets/                     # optional local images/data used by problems
```

## Problem files

`problem.md` is the default blind prompt packet. It should be solver-mode neutral: no no-skill wording, no `reasoning-graph`-specific instructions, no machine-specific paths.

Recommended sections:

1. Title
2. Short context / source note, if useful
3. `## Problem questions`
4. Case/puzzle material
5. `## Constraints`, only when constraints are intrinsic to the puzzle

For ordered variants, use `problem.vN.md` names. Keep `problem.md` as the default/v1 packet; use `problem.v2.md`, `problem.v3.md`, etc. for harder or revised variants. If a descriptive label matters, explain it in the scenario README or validator notes instead of the filename.

## Prompt templates

Share prompt templates in `_templates/`; do not duplicate solver-mode instructions inside each scenario.

Current templates:

- `_templates/no-skill.md` — baseline run without the skill.
- `_templates/reasoning-graph.md` — skill run using strict/graph mode.

Templates use `{{PROBLEM_FILE}}` as the problem path placeholder.

## Validators

`validator.md` is spoiler-only and must never be included in blind solver prompts.

Recommended validator sections:

1. `# SPOILER Validator — <scenario title>`
2. Short warning not to show it to blind solvers
3. `## Expected best solution` or `## Expected final answer`
4. Required evidence / clue coverage
5. Acceptable variants
6. Common wrong answers or scoring notes, if useful

Keep validators in Markdown for human review. Add machine-readable validator files only when a runner needs them; if so, put them beside `validator.md` with explicit names like `validator.json`.

## Running an arm

`tests/scenarios/bench.sh` runs one arm on one scenario:

1. `bench.sh prepare <scenario> <arm> <run-id> [problem-file]` creates a scratch workspace outside the repo (default `/tmp/rg-bench/<scenario>/<arm>/<run-id>/`). It holds only the problem file, any assets, the rendered `prompt.md`, and `meta.json` with the skill commit. The agent works there so it cannot read `validator.md` or the skill source.
2. Start the agent with that workspace as its cwd and its session log in `<workspace>/session`, then send `prompt.md` as the first message. For pi: `pi --session-dir <workspace>/session`.
3. `bench.sh collect <scenario> <arm> <run-id>` copies the workspace (answer, graph state, transcript) to ignored `test-results/<scenario>/<arm>/<run-id>/`.

Keep the skill commit fixed across the runs being compared; `meta.json` records it.

## Run metrics

Score every run on the same sheet, whichever arm produced it:

- core answer correct (per `validator.md`)
- clue-cluster coverage and fabricated-evidence count (claims in the final answer with no source in the transcript)
- tokens, peak context, wall time, tool calls

For reasoning-graph runs, also record from the stopped state:

- `reasoning-graph audit` stats: `pops`, `expansions`, `rankings`, and `peak_live_frontier`
- number of `contradicts` edges, and which stop gate the `stop` event names
- `validate` / `audit` / `stop-review` verdicts

Flag a run as **graph not exercised** when `peak_live_frontier` is 1 on a scenario that has an interpretation step (competing encodings, mappings, readings). Such a run says nothing about the skill's frontier queue and must not be counted as evidence for or against it.

## Assets

Put local images or auxiliary data under `assets/` inside the scenario directory. Reference them with relative paths from the problem file, e.g. `![caption](assets/image.png)`.
