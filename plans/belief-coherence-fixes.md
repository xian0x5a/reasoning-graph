---
status: active
---

# Belief coherence fixes (issues #1–#5)

## Goal

Fix the five belief-model issues filed after a wallet-drain case rendered two incompatible hypotheses at 81% and 80%:

- #1 the evidence-edge rubric asks relevance, the math reads a likelihood ratio
- #2 rival hypotheses share no scale
- #3 no workflow step checks belief coherence
- #4 `supports` vs `leads_to` silently flips belief direction
- #5 a user-rejected answer can still render at 95% (score-5 contradiction is only ÷5)

## Intention

The page's beliefs exist so a reader can catch a wrong weight (ADR 0010). Each fix makes the scores mean what the math does with them, or shows the reader an incoherence, without showing the writing agent a number to tune.

## Scope & Constraints

- The writing agent stays blind to belief; no audit check on belief (ADR 0010).
- Keep the five-step table and the ÷5 ceiling for evidence (ADR 0009).
- No normalization of beliefs (rejected in #2: makes survivors win by elimination, hides the signal).
- No compatibility paths: new fields and edge types are additive; reword docs in place.
- Branch `fix/belief-coherence`; one commit per layer.

## Work Plan

Layers, each working end to end before the next:

1. **Docs (#1, #4, #5 step 1 relabel, #3).**
   - `SKILL.md` and `docs/cost-model.md`: edge column becomes a diagnosticity question; "equally expected → no edge"; score 5 "very strong"; correct "no command prints belief" (`mermaid`/`html` render it for readers).
   - `SKILL.md`: rule for `leads_to` (premises that must all hold; a claim that combines or restates claims) vs `supports` (independent corroboration); reword the test-result sentence.
   - `SKILL.md` + new `docs/review.md`: optional pre-claim review by a read-only subagent that reads rendered beliefs and reports facts about the evidence, one round, never numbers, never a gate.
2. **`rules_out` edge (#5 step 2).** Observation → hypothesis/candidate_solution, no score, not groupable. Belief walk caps the target at `RULED_OUT_BELIEF` (renders `<1%`); `leads_to` descendants inherit it. Page/index/mermaid show "rules out" instead of a ratio; case "Against it" and Rivals include it. Rejection flow in `SKILL.md` uses it. ADR 0014.
3. **`exclusive_sets` (#2).** Top-level `exclusive_sets: [{id, members, note?}]`, patch `exclusive_sets` (upsert by id) and `remove_exclusive_sets`. Members: ≥2 distinct existing hypothesis/candidate_solution ids. Page: a section listing each set with members' beliefs; a reader-only note when two or more members are above 50%. Index lists sets. ADR 0015.
4. **Strong-contradiction mark (#5 step 1).** A claim with a score-5 `contradicts` edge or score-5 contradicts group shows the mark in its graph label and detail card, naming the source.
5. **Deduction rule (review round 3, N1–N5).** Three doc reviews kept finding leaks in the case list that splits `leads_to` from `supports`, so the split becomes one question, stated once in `SKILL.md`: if every source were certain, would the target be certain? Yes: `leads_to`, a deduction. No: evidence, scored by likelihood ratio.
   - Code: `record`/`refresh`/`audit` reject a `score` on a claim with belief-bearing `leads_to` premises or a `leads_to` group, naming the claims and the two ways out (unset it; or it is not a deduction: use `supports`, or add the doubt as a premise hypothesis). Removes the trap where a lemma scored 2 while open dropped to 27% once proved. ADR 0016 amends ADR 0009.
   - Docs: the rule lives in `SKILL.md` "Choosing the edge"; `cost-model.md`, `schema/tests.md`, `schema/goals.md` and `review.md` refer to it. Also N1 (review example), N3, N4, N5.
   - Rename of `leads_to` (to `premise_of`, with a separate test-to-result edge) is a follow-up issue, not this branch.

## Validation

- Existing suite: `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q` (baseline 409 passed).
- An independent agent writes behavior tests for layers 2–4 from the spec above, not from the implementation.
- Rerun the wallet-drain state and the bank-robber s55-loop-r2 round-3 state with `rules_out` replacing the user `contradicts` edges; rejected candidates should render `<1%`.
- Independent final review (Fable) of the whole branch.

## Progress

- [x] Branch created, baseline tests pass.
- [x] Layer 1 docs (2cd8edd)
- [x] Layer 2 rules_out (41cd31b)
- [x] Layer 3 exclusive_sets (17b3a58)
- [x] Layer 4 strong-contradiction mark (95967c8)
- [x] Independent tests: 36 tests from the spec, no bugs found (0fd12d1)
- [x] Independent review (Fable): 3 serious, 3 moderate findings, fixed with regression tests that fail on the pre-fix code (48808bb)
- [x] Doc reviews of the scoring wording: Fable (45defff), then Opus: fix first (N1–N5)
- [ ] Layer 5: independent tests for the deduced-claim score rule, written before the code and seen failing
- [ ] Layer 5: code, ADR 0016, existing tests and fixtures updated
- [ ] Layer 5: docs (deduction question, N1, N3–N5)
- [ ] Layer 5: independent final review
- [ ] Follow-up issue: rename `leads_to`

## Surprises & Discoveries

- The first `rules_out` cap leaked: a `leads_to` group replaced the ruled-out member's cost (descendant at 90%), and stacked support lifted a descendant from an inherited 0.001 (76%). The cap now covers the transitive `leads_to` closure and applies after evidence.
- A claim-sourced score 5 contradiction never divides by 5 (at belief b it divides by 1 + 4b), so the ÷5 mark counts only observation sources.
- The extra label line needed taller offline SVG nodes.

## Decisions

- Exclusive-set warning fires when two or more members exceed 50%, not when the sum exceeds 100%: with the 0.5 default, five rivals already sum to 250% before evidence, so a sum check would fire on every new set. Two members above 50% is impossible for exclusive claims whether or not the list is complete.
- No 1/n prior advice: it assumes the list is complete, and with a shared default the order inside a set barely depends on the prior.
- `rules_out` is a status edge, not a steeper ratio: any finite ratio loses to stacked support or a strong `leads_to` premise (advisor replays: ÷20 still left 12 of 77 rejected candidates at ≥50%).
- `audit` fails an answer that names a ruled-out candidate (reversed after review): leaving it out made `rules_out` gate less than the `contradicts(5)` it replaced. It reads the authored edge, not belief, so ADR 0010 holds.
- Name `exclusive_sets`, not `rival_sets`: the case page already has a "Rivals" part for candidates of one goal.

## Outcomes & Retrospective

- All five issues are addressed on `fix/belief-coherence`. Suite: 409 → 452 tests passing.
- The bank-robber round-3 state with `rules_out` renders its three rejected candidates at `<1%` (were 95%, 97%, 92%). The wallet-drain state before its fix gets the exclusive-set note (H1 81%, H2 80%); after the fix it does not.
- Decisions live in ADR 0014 (rules_out) and ADR 0015 (exclusive sets); the reviewer brief in `skills/reasoning-graph/docs/review.md`.
- Not done: an exclusive set id may equal a node or factor id (factors behave the same); left as is.
- Lesson: an independent review of the status semantics found what the spec-driven tests could not, because the spec itself had the hole.
