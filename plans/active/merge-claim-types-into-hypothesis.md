# Merge claim node types into `hypothesis` and rename `evidence` to `observation`

## Goal

Replace the node types `assumption` and `derived` with one type, `hypothesis`, and rename `evidence` to `observation`, across schema, package, docs, fixtures, tests, and scenario templates. One breaking release, no compatibility aliases.

## Intention

Since ADR 0003 the belief contract is type-blind: any claim node may carry a local prior, a posterior, `leads_to` premises, or a joint factor. `assumption` and `derived` therefore share every mechanic, and their names encode a retired contract (`derived` reads as "already established", `assumption` as "taken as given"). An intermediate claim that is asserted first and proved later, the lemma pattern, fits neither name, and the docs steer agents into duplicating such a claim as an assumption plus a later derived node.

`hypothesis` covers both roles: a competing interpretation you branch on, and an intermediate step you set out to establish. It names the loop the tool runs (hypothesis, test, observation, belief update) and invites the test step. `observation` replaces `evidence` because the most common trace failure is an interpretation recorded as evidence; the new name pushes the agent to record what was seen. The statistical term "evidence" stays in likelihood formulas.

Resulting node types: `goal`, `observation`, `constraint`, `hypothesis`, `test`, `candidate_solution`.

## Scope & Constraints

- Package under `packages/reasoning-graph/`; skill docs under `skills/reasoning-graph/`; ADRs under `docs/adr/`; scenario templates under `tests/scenarios/`.
- Breaking schema change. Remove the old type names entirely; no aliases, no migration code. Bump the package version.
- Belief contract, cost engine, frontier ranking, stop gates, and audit semantics are unchanged. Only names and the two rules below change.
- Existing ADRs are immutable records; ADR 0005 states the new names and notes that ADR 0003's type names are historical.
- Tests first for the two behavior changes; the rest of the test updates are mechanical.

## Decisions

- **Test results are observations only.** `RESULT_NODE_TYPES` becomes `{"observation"}`. A test result is what was observed; a conclusion drawn from it is a separate `hypothesis` linked by `leads_to` from the observation. Fixtures that recorded a `derived` result retype that node as `observation`.
- **No `hypothesis -> goal` edge.** Extends the former `assumption -> goal` rule. Claims reach goals only through `candidate_solution --answers--> goal`.
- **Role guidance lives in docs, not types.** Competing interpretations are sibling hypotheses: atomic, each with its own frontier item, re-ranked against each other. An intermediate step on a route is a hypothesis with its own sub-search and may be compound. A blocker is a hypothesis backed by observations. The lemma lifecycle is one node: prior while open, `leads_to` premises once proved.
- **Name choice.** `hypothesis` over `claim` because ADR 0003 and the cost model already use "claim" as the umbrella for every belief-bearing node. `observation` over adding it beside `evidence` because two names for one mechanical role is an ambiguity bug.
- **Proof-shaped tasks** get a vocabulary table in `docs/schema/goals.md`: theorem is `goal`; axiom or given is `observation` with prior 1.0, or `constraint`; lemma, proposition, corollary, and conjecture are `hypothesis`; proof is `candidate_solution` with `exact_method`; remark is report text.

## Work Plan

1. Package (schema, models, validation, audit, render, CLI messages, fixtures, tests):
   - Add failing tests: `hypothesis -> goal` edge rejected; a `test --leads_to--> hypothesis` result rejected under strict policy, `test --leads_to--> observation` accepted.
   - Rename types in `state.schema.json`, `models.py` (`NODE_TYPES`, `BELIEF_NODE_TYPES`, `RESULT_NODE_TYPES`, class map), `validation.py`, `audit.py`, `render.py`, `offline_render.py` (one hypothesis cluster and color; observation cluster), `cli.py` help text and messages.
   - Update every fixture under `tests/fixtures/` and every test. Add negative fixtures for the two new rules to the fixture matrix.
   - Bump version in `pyproject.toml`.
2. Skill docs (`skills/reasoning-graph/SKILL.md`, `docs/schema/*.md`, `docs/cost-model.md`, `docs/driver.md`, `docs/rendering.md`), root `README.md`, `tests/scenarios/_templates/*.md`, scenario validator prompts:
   - Rename types in prose, JSON examples, and edge-direction rules.
   - Replace the assumption/derived role text with the role guidance above; add the lemma lifecycle example and the proof vocabulary table to `goals.md`.
   - Test result pattern: `claim --prompts--> test`, `test --leads_to--> observation`, `observation --supports|contradicts--> claim`.
3. ADR 0005 `node-types-name-observation-and-hypothesis-roles.md`.

Steps 1 and 2 touch disjoint files and run in parallel.

## Validation

- `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q` green.
- `grep -rw 'assumption\|derived\|evidence'` over package source, schemas, fixtures, skill docs, and templates returns only the statistical use of "evidence" in likelihood formulas and historical ADR text.
- The SKILL.md patch example runs through `init --strict`, `seed`, `next --pop`, `expand` with a test result, and `validate` with the installed CLI.
- README smoke flow runs.

## Progress

- Plan written.

## Surprises & Discoveries

## Outcomes & Retrospective
