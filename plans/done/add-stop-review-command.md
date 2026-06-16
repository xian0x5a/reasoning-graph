# Add Semantic Stop Review Command

## Goal

Add a lightweight `rg.py stop-review` command that runs final-stop checklist diagnostics before promoting a stopped state/final answer.

## Intention

Encode the docs' semantic stop-review gate as a practical command. It will not prove the answer true, but it should catch missing stop events, missing/invalid selected candidates, validation/audit failures, and obvious draft/state mismatches.

## Scope & Constraints

- Follow pseudocode-first for `cli.py`.
- No LLM calls or new runtime dependencies.
- Keep command conservative: structural/semantic checklist only.
- Existing `validate`/`audit` remain canonical.

## Work Plan

1. Update CLI pseudocode.
2. Implement `stop-review STATE [--draft PATH] [--strict-warnings]`.
3. Output YAML-like verdict: `pass|fail`, `required_fixes`, `semantic_tricks_checked`, `notes`.
4. Add tests for pass and fail cases.
5. Update docs and run validation.

## Validation

- `python -m py_compile skills/reasoning-graph/scripts/rg.py skills/reasoning-graph/scripts/reasoning_graph/*.py`
- `python -m unittest discover -s tests/scripts`
- `python skills/reasoning-graph/scripts/rg.py validate tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py audit tests/reasoning-graph-strict-good.json`
- `python skills/reasoning-graph/scripts/rg.py stop-review tests/reasoning-graph-strict-good.json`

## Progress

- Started after CLI starter commit `4c1fae5`.
- Updated CLI pseudocode.
- Implemented `stop-review STATE [--draft PATH] [--strict-warnings]`.
- Added YAML-like verdict output with required fixes, checked tricks, and notes.
- Added tests for fixture pass, missing selection failure, and draft comparison.
- Updated README, `SKILL.md`, and driver command docs.
- Validation passed: py_compile, unittest suite, fixture validate/audit/stop-review.

## Outcomes & Retrospective

- The documented semantic stop-review gate is now executable.
- Command remains conservative: it catches structural semantic issues but does not claim to prove answer truth.
- `--strict-warnings` lets benchmark flows fail on validation/audit warnings.
