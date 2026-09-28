# Refresh command and tamper-evident stop gate

## Goal

Give agents one explicit command that recomputes a hand-edited state, and make `stop` compute everything it checks itself, so a hand edit can't slip past the gate.

## Intention

`e4d4f83` made a `record` whose patch holds only a reason do the re-sync. The user rejected that as unclear and asked for an update-like command. The user also asked that the pass check recompute on its own, to avoid cheating.

Gaps in `stop` today:

- It never validates the graph.
- It writes whatever stored beliefs it finds into the stopped state.
- Review staleness is "any `record` after the review", so a Python hand-edit made after a passing review goes unnoticed.

## Scope & Constraints

- **Graph digest.** A short sha256 over nodes (minus `belief`), edges, and factors, each sorted by id, plus `stop_policy`, `goal_policy`, and `goal_groups`. `record`, `refresh`, `review`, and `stop` events store it as `graph_digest`.
- **`reasoning-graph refresh <state>`:**
  - drops stored beliefs, validates, and rechecks every quote;
  - logs as removals any traced object that's gone;
  - writes fresh beliefs and the view;
  - appends a `refresh` event only when the digest differs from the last `record`/`refresh` event.
- **`record`** refuses a state whose digest differs from the last `record`/`refresh` event and names `refresh`. The reason-only re-sync is removed.
- **`stop`** recomputes beliefs and validates the graph first. It refuses when the digest differs from the last `record`/`refresh` event. It writes fresh beliefs, and the stop event carries the digest.
- **Review staleness:** the latest review's digest must equal the current digest. This replaces the "record after review" index rule.
- **`audit`:**
  - the current digest must equal the stop event's digest, so an edit after `stop` is caught;
  - the claim replay includes `refresh` events.
- **Schema:** `refresh` action; `graph_digest` required on `record`, `refresh`, `review`, and `stop` events. Fixtures get digests; no compatibility path.

## Work Plan

1. Tests: patch-op tests stay in `tests/cli/test_patch_operations.py`. Hand-edit and anti-cheat tests go in `tests/cli/test_hand_edits.py`. Watch them fail.
2. CLI: digest, `refresh`, the `record` and `stop` sync checks, review staleness, audit, schema, fixtures.
3. Docs: `SKILL.md`, `docs/driver.md`, ADR 0008 (not yet pushed, so edit it in place).

## Validation

- Full package suite.
- Smoke on the reinstalled tool, in order:
  1. A hand edit after a passing review is refused by `stop`.
  2. `refresh`, then `stop` again: refused as the graph changed after the review.
  3. Re-review, then `stop` passes; `audit` passes.
  4. Edit the stopped state: `audit` fails.

## Decisions

- The digest leaves out `belief`, because `stop` overwrites beliefs with computed values anyway, so a forged belief changes nothing.
- It also leaves out `summary`, `report`, and `presentation`, which carry no gate input.
- `refresh` takes no reason: the event records removals and the digest, which is what the trace needs.

## Progress

- [x] 1. Tests
- [x] 2. CLI
- [x] 3. Docs

## Outcomes & Retrospective

- CLI: `75f68e4`; docs in the next commit. Suite: 326 passed.
- Smoke on the reinstalled tool, in order:
  1. A Python prior bump after a passing review was refused by `stop`, which named `refresh`.
  2. After `refresh`, `stop` was refused because the graph changed after the latest review.
  3. After a new review, `stop`, `audit`, and `stop-review` all passed.
  4. Editing the stopped state made `audit` fail with "the graph changed after stop".
- Surprise: 11 existing tests hand-built or hand-edited states and then called `stop` or `audit`. They now go through `refresh`, or stamp digests on forged events, the same path agents take.
- Surprise: `stop` never validated the graph before. It now does, so an invalid graph fails with the validation error instead of a gate message.

## Superseded in part

`record` and `stop` no longer refuse a hand-edited graph. They run the same checks as `refresh` and log the edit, because the review gate already catches a hand edit made after a review, so refusing only cost a turn.
