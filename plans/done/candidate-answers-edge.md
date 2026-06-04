# Candidate answers edge

## Goal

Introduce `answers` edge type for `candidate_solution -> goal`. Keep `leads_to` for derivation/progression between non-answer nodes.

## Constraints

- `answers` edge must connect `candidate_solution` to `goal`.
- Candidate viability and goal targeting use `answers` edges only.
- `contradicts` remains general penalty semantics; remove candidate-specific downrank wording from skill docs.
- Update docs, helper schema/policy/validation, fixtures, and tests together.
- Preserve CLI command behavior.
- Pseudocode-first active: update mapped pseudocode before source edits.

## Plan

1. Update tests/fixture to require `answers` for candidate-goal links and reject candidate-goal `leads_to`.
2. Update pseudocode artifacts for models/policy/validation.
3. Patch scripts:
   - models: add `answers` edge type.
   - policy: candidate-goal targets resolve via `answers`.
   - validation: candidate-goal `answers` required; `answers` only valid from candidate to goal.
4. Patch `SKILL.md` wording/examples.
5. Run unit tests, py_compile, validate, audit.

## Progress

- [x] Plan created.
- [x] Tests/fixture updated first; failures confirmed helper still expected `leads_to`.
- [x] Pseudocode artifacts updated before source edits.
- [x] Helper scripts patched for `answers` edge type.
- [x] `SKILL.md` patched for `answers` semantics and simpler contradiction wording.
- [x] Unit tests, py_compile, validate, and audit passed.

## Decisions

- Edge type name: `answers`.
- Do not keep `leads_to` as valid candidate-goal syntax.
- Do not add candidate-specific contradiction/downrank guidance beyond general `contradicts` rule.

## Blockers

None.
