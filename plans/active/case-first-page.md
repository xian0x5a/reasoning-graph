# Case-first page

The build half of #39, together with the refactor of #18. The reader eval of #39 is the last step and gets its own plan once the page exists.

## Goal

A person who opens the page can check the answer without reading the graph first:

- why the answer should be believed, down to the verbatim quote of each observation
- what counts against it
- what was tested, and what came back
- which rivals were considered, and how they rank
- where the record is thin

The graph stays on the page as the full record, and it is readable when it opens.

## Intention

The page today leads with a one-line answer, then a full-graph canvas, then one card per node. A 26-node graph opens as a thin strip of unreadable nodes (Mermaid) or a long column of observations with overlapping edge labels (offline). The reader has to rebuild the argument from the canvas. #39 guessed the page should lead with the proof path of the named answer. The user chose that shape on 2026-09-29, over a split view and over keeping the graph first.

Both renderers repeat the same helpers (`clip_text`, `html_anchor`, the compact node label) and each works out node classes, beliefs and labels by itself. The new outline needs the same facts a third time. That is the moment to do #18: one normalized graph that the outline, Mermaid and the offline SVG all read.

## Scope & Constraints

In scope:

- #18: a shared visual graph model, and the split of `render.py` into Mermaid, page, and browser assets.
- The case: a pure function from the state to the case for the claimed answer, and its section on the page.
- The page reorder: case first, graph second, node details collapsed.
- Graph legibility: the Mermaid canvas opens readable, and the offline SVG no longer stacks every observation in one column.

Out of scope:

- The reader eval (time and hit rate against the notes file). Next plan.
- A split view with the graph beside the outline. Can be added on top if the eval asks for it.
- Any change to the state, the schema, `audit`, or the agent-facing commands.

Constraints:

- The case shows only what the graph and the claim say (ADR 0013). No text is written for the reader outside the nodes and edges.
- Belief stays computed at render time (ADR 0010).
- Tests first for behaviour that can regress: the case derivation and the shared model. Screenshots for layout.
- True Detective texts stay out of git. Test states are written by hand.

## The case

For the answer of each answered goal. Nothing is shown while no answer is claimed.

| Part | Derived from |
| --- | --- |
| Why believe it | incoming `leads_to` and `supports` edges, walked from the answer down to observations. Each line: edge type, authored score or group score, node id, text, and for an observation its source and verbatim quote. A node already shown is referenced, not repeated. |
| Against it | `contradicts` edges into the answer or into any node of its why-tree, with the same detail |
| Tests | test nodes linked by `prompts`/`tested_by`/`tests` to a node of the why-tree, with each result observation (`test leads_to observation`) or the `not_run` reason |
| Rivals | the other candidates of the same goal, by computed belief, each with its contradicting edges |
| Weak spots | mechanical only: a test of the why-tree that was not run; an observation of the why-tree without a quote; a claim of the why-tree that rests on one input (`leads_to` or `supports`, a group counts once) or on none |

These are the edges belief flows through (`costs.truth_inputs`), so the outline and the computed belief tell the same story.

## Work Plan

1. **Shared visual graph (#18).** `graph_view.py` builds, once per render, the nodes (render id, anchor, type, class, group, label lines, belief, answer label) and the drawn edges (ends, type, dashed or not, factor membership). `to_mermaid` and `offline_graph_svg` read it. The duplicated helpers go. Output unchanged: the existing render tests pass as they are, plus one test that both renderers draw the same nodes and edges from a shared fixture.
2. **Split `render.py` (#18).** `mermaid.py` holds `to_mermaid`; `page.py` holds the document; the CSS and JS move to package files under `page_assets/`, and the page passes its data to the script as JSON. Output unchanged apart from where the script reads its data.
3. **The case.** `case.py` returns the case as plain data. Tests on hand-written states cover each part, shared premises, groups, and a state with no answer.
4. **Case-first page.** The case section follows the answer and status. Each id in it opens the node's popup. The graph follows; node details go into a closed `<details>`. `rendering.md` describes the new page.
5. **Legible graph.** Mermaid: pick the layout direction and canvas fit so a 26-node real state opens with readable labels. Offline: wrap a tall rank into several columns and keep edge labels apart. Checked by screenshot on three real states (10, 26, 32 nodes).

Commit after each step.

## Validation

- Package checks pass: `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`.
- Steps 1 and 2 leave the rendered HTML of the fixtures unchanged, except where step 2 moves the data into JSON.
- Screenshots of real states of `s55-loop-r3` in both modes, read at desktop and phone width. Outputs stay in `/tmp` or the job directory.

## Progress

- [x] 1. Shared visual graph (96cd100). Mermaid output unchanged except the unused `bad` class; the offline SVG now paints from the shared palette.
- [x] 2. Split `render.py`. Mermaid, markup, CSS and page data unchanged on the fixtures and two real states; the script reads its data from `#page-data`.
- [x] 3. The case. `case.py` `answer_cases(state)`; `tests/integration/test_case.py`. Checked by hand on sweat-it-out r3 and the-anonymous-bank-robber r4.
- [x] 4. Case-first page. `case_section.py`; `tests/integration/test_case_page.py`. Checked in headless Chrome at 1400px and 390px on sweat-it-out r3; a clicked case id opens its popup in both modes.
- [ ] 5. Legible graph

## Surprises & Discoveries

- Moving the JS out of a Python f-string kept its doubled backslashes (`/\\s+/`). No test caught it; the golden diff of the script text did. The page now runs identically in headless Chrome (same edge hitbox count, both modes).
- A module script runs only after its imports load, so case links set up inside the Mermaid bootstrap would wait on the CDN. `setupPage()` (case links, popups, filters, nav) now runs in the classic script; `setupGraphs()` still waits for the drawn graph.
- A local `uv build` reuses the ignored `packages/reasoning-graph/build/`, so a wheel can carry a deleted module. A git install starts clean.

## Decisions

1. The page leads with the case (user's choice, 2026-09-29).

   | Option | Reader checks the answer fast (×3) | Works on a phone (×1) | Build cost, low is 5 (×2) | Measurable against notes (×2) | Total |
   |---|---|---|---|---|---|
   | Case first | 5 | 5 | 4 | 5 | 38 |
   | Split view | 5 | 2 | 2 | 4 | 29 |
   | Graph first, fixed | 2 | 3 | 5 | 2 | 23 |

2. #18 goes first. Every shape needs the same node facts, so the shared model does not depend on the page design.
3. Weak spots are mechanical. A judgment such as "a weak clue scored 5" is the reader's to make, and the eval measures whether the page helps them make it.
4. A claim with no input at all is a weak spot too (`no_input`), next to one resting on a single input. Both are counts, so the rule stays mechanical.
5. Tests are listed in node order, and linked either way: a why-tree node prompts or is checked by the test, or the test produced a why-tree observation (`test leads_to observation`).

## Outcomes & Retrospective
