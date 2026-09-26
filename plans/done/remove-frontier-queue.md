# Remove the frontier queue from the CLI

## Goal

Delete the best-first frontier queue from the `reasoning-graph` package so the CLI only does what the skill now asks of it: record the graph as memory, render the live view, and gate the stop on a grounded, confident, reviewed answer.

## Intention

The countdown-island benchmark (issue #33) showed the queue and the rival gate pulled agents into seeding and popping work they did not need, which cost quality and tokens. The skill (`skills/reasoning-graph/SKILL.md`, commit 750d4a3) no longer uses the queue; the CLI still ships it. Dead machinery confuses agents that read `--help` and doubles the test surface.

## Scope & Constraints

Remove:

- Commands: `seed`, `next`, `assign`, `expand`, `frontier`, `sort`, `path`, `rank` (standalone).
- State: `frontier`, `search_policy`, `view.frontier`; queue events `init`, `seed`, `pop`, `assign`, `expand`, `supersede`.
- Stop outcome `frontier_exhausted`; stop_policy fields `max_live_frontier_items`, `require_frontier_exhausted_for_epistemic_stop`.
- Code: search-cost ranking in `costs.py` (`search_policy_*`, `estimated_remaining_*`, `cost_components_for_item`, `sorted_frontier*`, frontier part of `compute_costs`); `frontier.py` queue logic (expansion signatures, item views, path reconstruction); `DEFAULT_MAX_PROBE_CONCURRENCY`, `SEARCH_COST_COMPONENTS`, `PROBE_LIKE_MARKERS`, `LEGACY_COST_COMPONENT_ALIASES`; queue branches and pop/expansion/breadth/peak-frontier stats in `audit.py`; frontier validation in `validation.py`; frontier class in `render.py`.
- Queue-only tests and fixtures (`invalid/audit/pending-pop-not-expanded.json`, pop/assign/supersede/concurrency/best-first tests).

Keep:

- `init`, `record`, `review`, `stop`, `validate`, `audit`, `stop-review`, `doctor`, `costs` (node beliefs only), `schema`, `mermaid`, `html`.
- Belief math in `costs.py`, all stop gates in `policy.py`.
- The `rank` event: `stop` still appends it for candidate outcomes, because `audit` and `stop-review` read the best candidate at stop time from it. Only the standalone command and `--item` go.

Constraints:

- No compatibility path: an old state carrying `frontier` or queue events fails `validate` (per `~/.agents/AGENTS.md` Legacy Handling). No migration command.
- Suite stays green at each milestone commit.
- Tests that used `seed`/`expand` only as a harness to build a graph are ported to `record`, not deleted; their belief, grounding, and gate assertions are the valuable part.

## Work Plan

1. **Port harnesses (queue still present).** Switch tests that build graphs via `seed`/`expand` but assert non-queue behavior to `record`: `test_score_commands` (parametrized `seed`/`expand` → `record`), `SpookyManorFlow` in `test_stop_gates`, belief/cost tests in `test_commands`, `test_belief_sources`, `test_driver_invariants`, `test_fixture_matrix::test_patch_fixtures_apply_to_popped_branch`. Convert fixtures `reasoning-graph-strict-good.json`, `strict-driver-state.json`, `stopped-reviewed-state.json` and the `invalid/*` fixtures to record/review/rank/stop traces with no `frontier`. Commit.
2. **Remove the queue.** Delete the commands, code, schema definitions (`frontierItem`, queue event variants, `search_policy`, `frontier_exhausted`), and queue-only tests listed above. Shrink `frontier.py` to trace status (`next_event_step`, initialized/stopped) and rename it `events.py`. `audit` keeps: record claim integrity, review validity, rank payload checks, stop gates at stop time. Regenerate goldens (`init-strict.json`, `doctor-strict-driver.txt`). Reinstall the tool. Commit.
3. **Docs.** `skills/reasoning-graph/docs/driver.md` (drop "Queue Driver Loop", command list, queue events), `skills/reasoning-graph/docs/cost-model.md` (drop search cost), `skills/reasoning-graph/docs/schema/reporting.md` (drop `view.frontier`), repo `docs/test-scenarios.md` (run metrics: records, reviews, stop gate instead of pops/expansions/`peak_live_frontier`; drop the "graph not exercised" rule). Add `docs/adr/0006-graph-is-memory-and-stop-gate-not-a-work-queue.md` with the benchmark results and the decision. Commit.
4. **Issue #33.** Draft a results comment; post only after the user confirms.

## Validation

- Full suite green after each milestone: `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`.
- `reasoning-graph --help` lists no queue command; `grep -rn "frontier\|search_cost\|pop" packages/reasoning-graph/src skills/reasoning-graph` returns only intended hits.
- End-to-end smoke on the reinstalled tool: `init --strict` → `record` ×2 → `review --verdict pass` → `stop --outcome solved` → `validate`, `audit`, `stop-review --draft` all pass, and `state.html` renders.
- A state with a `frontier` key fails `validate` with a clear error.

## Failure cases considered

- **Stop loses the best candidate.** If the rank event went with the `rank` command, `stop-review` could not check that the answer names the best candidate. Mitigation: `stop` keeps appending it.
- **Audit loses tamper checks.** Queue events carried the add-claims audit replays. Mitigation: `record` events already carry `add_nodes`/`add_edges`/`update_factors`; the replay keeps working on them.
- **Old benchmark states stop validating.** Accepted: they live under ignored `test-results/` as evidence, not inputs.

## Decisions

- `min_viable_candidates` + `candidate_count_met` stay as an opt-in for when the user asks for N alternatives; `init --strict` never sets it. It is detached from `max_live_frontier_items`.
- `costs` stays, reporting node beliefs only.

## Progress

- [x] 1. Port harnesses (committed with 2 as 0bb5c71)
- [x] 2. Remove the queue (0bb5c71)
- [x] 3. Docs + ADR 0006
- [x] 4. Issue #33 comment posted: https://github.com/ewgdg/reasoning-graph/issues/33#issuecomment-5843212311

## Surprises & Discoveries

- Milestones 1 and 2 could not be split: the opt-in `min_viable_candidates` check lived in `audit_stop_policy` behind the live-frontier count, so record-trace fixtures could not pass until audit was rewritten. Committed together.
- `compute_costs` only annotated frontier items, so `costs` became a no-op without a queue; replaced by a read-only `beliefs` command.
- With `rank` written only by `stop`, audit's historical replay and the record-event snapshots it needed were dead; removed.
- State schema allows extra top-level keys, so `frontier`/`search_policy` are rejected through the existing legacy-field `not`/`required` rule.
- `doctor` failed on every working state once `record` created events from step one (audit needs a stop); it now audits only stopped states.
- `report.candidates[].search_cost` and the HTML "Search" column were queue leftovers; removed.

## Outcomes & Retrospective

- CLI surface: `init`, `record`, `review`, `stop`, `validate`, `audit`, `stop-review`, `doctor`, `beliefs`, `schema`, `mermaid`, `html`.
- Tests: 313 pass (369 before; the difference is queue-only tests). A subagent ported `tests/cli/test_commands.py`.
