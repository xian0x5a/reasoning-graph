# Graph-centric state and page

Part 1 continues the pruning of #38. Part 2 is a first step of #39.

## Goal

The state is the graph, and the page shows the graph. Nothing is kept or shown as a second copy of what the nodes and edges already say.

## Intention

`report`, `presentation` and `view` let an agent write the answer, the candidates and the winning path a second time, beside the graph. A copy can disagree with the graph, so it needed checks of its own. No agent used it: in the final states of `s55-loop-r1`, `r2` and `r3` (42 states) none of the three keys appears. The page still had sections built for them, and its answer line printed the bare id.

The one fact the graph does not hold is which candidate is claimed. That stays, as `summary.answer`.

## Scope & Constraints

In scope:

- Part 1: remove `report`, `presentation` and `view` from the state, and what reads them.
- Part 2: the page header, the removal of the candidate table, and a label on the answer node.

Out of scope:

- The presentation eval of #39: no reader is measured here.
- What the page leads with. The full graph stays the one canvas.
- A benchmark rerun. No agent wrote these keys, and no agent opened a render.

Constraints:

- Breaking change to the state and to `mermaid`. No compatibility path.
- Tests first for each behaviour, seen failing for the expected reason.
- True Detective texts stay out of git. Test states are written by hand.

## Work Plan

### 1. State prune

- A state that carries `report`, `presentation` or `view` fails validation with a message that says where the content goes: a reason is a `note`, a next check is a `test` node, the answer is `summary.answer`.
- Removed with them: the checks on `report.answer`, report rows and the winning path; the reference checks on `presentation` and `view`; `mermaid --view` and `--grouped`.
- The page loses the sections that only `report` filled: the insight cards and "Best next verification".
- `docs/schema/reporting.md` is deleted. ADR 0013 records the decision.

### 2. Page

- The header has one line per answered goal, resolved from the graph: `Answer: CS1, <candidate text>`. With no answer claimed there is no answer line; the status line says so.
- The "Candidate ranking" table is removed. The belief of a claim is on its node.
- The answer node carries a text label in both renderers, and so does its option in the focus dropdown.
- The status line and the note on an answer that is not top-ranked stay.

## Validation

- Package checks pass: `uv --project packages/reasoning-graph run --group dev pytest packages/reasoning-graph/tests/cli packages/reasoning-graph/tests/integration -q`.
- One real state of `s55-loop-r3` renders in both modes, and a screenshot of each is read. Outputs stay in `/tmp`.

## Progress

- [x] 1. State prune (`55047bd`, docs and ADR 0013 in `971a17e`)
- [x] 2. Page (`3b02ec5`, `cac3706`, `9d2176a`)

## Surprises & Discoveries

- **Node filtering had no caller left.** `include_nodes` and `group_by_type` of both renderers served only the presentation view, so they went with it.
- **Mermaid drew empty group boxes.** `cluster_factors` and `cluster_other` appeared beside the graph of a state without factors. Older than this plan, found in the screenshot, fixed in `9d2176a`.

## Decisions

1. `report`, `presentation` and `view` are removed whole. They were never written in 42 states, and each was a copy of the graph that needed its own checks.
2. `summary.answer` stays. It is the claim, and the rule that a goal's only candidate is its answer was removed in #38.
3. The page keeps one answer line. Without it a reader has to find the conclusion in a graph of 40 nodes.
4. The answer node is labelled, not highlighted, and its path is not highlighted either. The focus dropdown highlights a path when the reader asks for it.

   | Option | Reader finds the answer fast (×3) | No copy of the graph (×2) | Fewer concepts (×2) | Total |
   |---|---|---|---|---|
   | Keep the report sections | 3 | 1 | 1 | 13 |
   | Graph-centric, one header line | 5 | 5 | 4 | 33 |
   | Graph only, no header | 2 | 5 | 5 | 26 |

## Outcomes & Retrospective

Both parts are done. The package check passes: 367 tests, 73 subtests. The change removes 750 lines and adds 291 over 23 files.

- **State:** a state that carries `report`, `presentation` or `view` fails validation, and the message says where the content goes.
- **Commands:** `mermaid` lost `--view` and `--grouped`. It always renders the full graph, grouped by type.
- **Page:** the header reads `Answer: CS3, <candidate text>`, then the status. The page then shows the graph and the node details. The candidate table, the insight cards and "Best next verification" are gone.
- **Answer label:** the node reads `CS3 · ANSWER`, or `CS1 · ANSWER to G1` with several goals. The detail card reads `candidate_solution · ANSWER`, and the focus option `CS3 (ANSWER)`. Nothing is highlighted until the reader picks a focus.

Checked on a real state of `s55-loop-r3` (26 nodes) in both render modes, by screenshot.

Seen in the screenshots and left alone, both older than this plan and both for #39:

1. Mermaid fits a wide graph to the width of the canvas. The nodes are small and most of the canvas is empty until the reader zooms.
2. The offline SVG puts all observations in one long column, and edge labels overlap where many edges meet.

Not measured: whether a reader finds the answer or an error faster. That is the eval of #39.
