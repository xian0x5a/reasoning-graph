# Split Reasoning Graph Skill Docs

## Goal

Reduce active `skills/reasoning-graph/SKILL.md` from reference-manual size to operational quickstart while preserving full reference material in linked docs.

## Intention

Make agents more likely to follow core workflow. Keep detailed schema/cost/rendering guidance available, but not forced into every skill activation.

## Scope & Constraints

- Documentation-only change unless validation reveals source/doc drift.
- Preserve behavior and command examples.
- Do not introduce machine-specific paths.
- Keep `SKILL.md` sufficient for first use and routing to references.
- Put detailed docs under `skills/reasoning-graph/docs/` so skill package remains self-contained.

## Work Plan

1. Extract reference sections into focused docs:
   - `schema.md`: node/edge/factor/goals/report metadata.
   - `cost-model.md`: priors/confidence/costs/likelihoods/bounded probes.
   - `driver.md`: helper commands, state shape, expansion patches, driver loop, audit/stop review.
   - `exploration.md`: ledger extraction, branching, candidate hygiene, stopping.
   - `rendering.md`: compact/graph output and HTML rules.
2. Rewrite `SKILL.md` as concise operational quickstart with links.
3. Validate no important guidance lost by comparing headings/keywords.
4. Run tests to ensure docs-only change did not affect helper.

## Validation

- `python -m unittest discover -s tests/scripts`
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`
- Manual check: `SKILL.md` line count materially reduced and docs contain extracted sections.

## Progress

- Started after committing P0 #1 as `57b7cc2`.
- Extracted reference sections into five docs under `skills/reasoning-graph/docs/`.
- Rewrote `SKILL.md` from 932 lines to 179-line operational quickstart.
- Validation passed: unittest suite, fixture validate, fixture audit.

## Outcomes & Retrospective

- Active skill prompt is now short enough for routine activation.
- Full reference content remains package-local in focused docs.
- No helper code changed.
