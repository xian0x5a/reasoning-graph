# Reasoning Graph Rendering Guide

Final prose, HTML artifacts, and visual presentation rules.

## Output Formats

### Default Final Response

Default. Return:

1. answer or recommendation
2. winning proof path as concise user-facing rationale
3. open hypotheses relied on, if any
4. top competing candidate paths when ambiguity matters
5. contradictions or heavily penalized branches only if important
6. next test/action if uncertainty remains

When also creating HTML/graph artifacts, write the user-facing answer first or keep it complete in the final response. The visual artifact is extra output, not a substitute for clear prose reasoning.

Do not expose hidden chain-of-thought or raw scratch state. Provide a clear proof path / reasoning summary suitable for the user.

Example compact shape:

```md
Answer: ...

Proof path:
E1 -> C1 -> A2 (score 4) -> D4 -> candidate S1

Why this wins:
- satisfies C1/C2
- lower search cost than S2
- test T1 supports A2

Other candidates:
- S2: possible, but needs expensive verification
- S3: contradicted by C2

Remaining uncertainty:
- verify T2 before treating S1 as final
```

### Graph/HTML Artifacts

Create when user asks for graph/visualization/HTML, or when agent recommends it and user approves.

Graph/HTML artifacts may have two useful views:

- `audit graph` — complete/debuggable reasoning graph; good for checking reasoning completeness.
- explanation view — concise human report, optionally a curated/lossy graph, good for communicating why the answer wins.

The full reasoning state is always the source of truth. An explanation view can omit nodes, but must not invent observations, constraints, candidate claims, or edges absent from the state.

Create an HTML artifact as a report, not a fixed template. Choose the layout that best explains the case/problem. It must include:

- the answer at the top: id and text of the answer candidate, resolved from the graph
- readable observation and constraint node details with labels/sources, either in a filterable detail list or modal cards
- a concise explanation view; this may be a curated graph or the full graph when it is already small/readable
- a full audit graph in a pan/zoom canvas when the graph is large or debugging transparency matters
- click-to-details for graph nodes, ideally without forcing the user away from the canvas
- the answer candidate labelled on its node; a path is highlighted only when the reader asks for it
- candidate solutions connect to the goal with `answers`
- contradicted/heavily penalized branches dimmed or red
- next verification/action when available

Artifact location:

- requested/durable artifact path first, when the user or task names one
- project artifact path only when useful or requested, e.g. `./docs/reasoning-graphs/<slug>.html`
- ad hoc fallback only: `/tmp/reasoning-graph-<slug>-<timestamp>.html`

`reasoning-graph html` uses Mermaid by default for better graph layout. `reasoning-graph html --offline` switches to deterministic inline SVG fallback for air-gapped/no-network contexts and keeps Mermaid source in collapsible source blocks. When the user or prompt asks for a reasoning graph, graph canvas, or an HTML report from this skill, the requested HTML output path must be generated from the validated state with `reasoning-graph html`. Custom self-contained SVG/HTML is allowed only as an additional artifact, or when the user explicitly asks for a bespoke non-helper report; do not replace the baseline graph/canvas report with a hand-written summary page.

For non-trivial HTML report generation, delegate presentation work to a low-thinking agent when possible. The solver should focus on the reasoning state; the renderer should consume `state.json` as source of truth and not solve again. If delegation is not available from the current context, write/validate `state.json` and clearly state that polished HTML rendering is a follow-up step for a low-thinking agent.

Delegation contract:

```txt
Read state.json. Generate polished self-contained HTML report. Do not solve again. Do not change reasoning. Do not invent observations. State JSON is the only source of truth. If data is missing, render conservatively or report missing fields.
```

Recommended graph/HTML flow:

1. Persist the graph/search state as JSON in the requested output path or durable artifact location; use `/tmp` only as an ad hoc fallback.
2. Build/update the state with `record` as work progresses (`../SKILL.md`); each `record` refreshes `<state>.html` as a live view.
3. Run `reasoning-graph audit state.json` and fix errors or explain remaining warnings.
4. Generate the requested graph HTML path with `reasoning-graph html state.json -o <requested-output>.html`. The helper emits the baseline canvas report with explanation/audit graph views, node-detail popup modals, filterable detail cards, and a candidate focus dropdown. Use `--spacing relaxed|wide|compact|default` to compare Mermaid/offline spacing presets. Add `--offline` only when network/CDN use is disallowed.
5. If you also want a custom/polished summary page, save it separately as `<slug>-custom.html` or similar. Never use a custom summary page as the only artifact when graph/HTML output was requested.
6. For separate graph sources, run `reasoning-graph mermaid state.json > <slug>.mmd`.
7. For polished presentation output, hand off `state.json`, optional `.mmd` files, optional style reference, and an extra output path to a low-thinking rendering agent. The renderer may design freely, but it must preserve the source-of-truth state and must not invent reasoning.
10. If network/external dependencies are disallowed, produce self-contained HTML/SVG or provide the `.mmd` plus a plain Markdown fallback.

### What the helper page shows

Everything on the page comes from the graph and the claim `summary.answer`. Top to bottom:

| Part | Content |
| --- | --- |
| Answer | one line per answered goal, `Answer: CS1, <candidate text>`; with several goals, `Answer to G2: CS3, <candidate text>`. No line while no answer is claimed |
| Status | the line `audit` prints, such as `answer CS1: checks pass`, computed when the page renders |
| Rank note | only when another candidate of the same goal outranks the answer |
| Case | the case for each answer, described below. None while no answer is claimed |
| Graph | the full graph, grouped by node type, in a pan/zoom canvas |
| Goal policy | only when the state has `goal_policy` or `goal_groups` |
| Node details | one card per node: text, source, quote, note, belief, edges. Collapsed at first |

A source whose first word names a local file, resolved beside the state as the quote check does, links to that file wherever it shows: in the node details and in the case's quotes. The reader opens it to see the context around a quote. The link is relative when the file sits in the page's directory or below it, since the two then move together, and an absolute `file://` URL otherwise, including a page written to stdout. A file missing when the page renders, and any other source, stays plain text. A symlinked file links to its target, so it is absolute unless the target also sits under the page.

### The case

The case lets a reader check the answer without reading the graph first. It lists nodes and edges only, no written summary. Each id is a chip in its node's colour, and clicking it opens that node's popup.

| Part | Content |
| --- | --- |
| Why believe it | the `leads_to` and `supports` edges into the answer, walked down to observations: edge type, the edge's or its group's score, id, text, belief of a claim, and an observation's verbatim quote and source. A node already shown reads `shown above` |
| Against it | `contradicts` edges into the answer or into any node of its why-tree, as `CS1 ← contradicts O6` |
| Tests | tests that a why-tree node prompts or is checked by, or that produced a why-tree observation, with each result observation or the `not_run` reason |
| Rivals | the other candidates of the goal, by belief, with the `contradicts` edges into each |
| Weak spots | counted, not judged: a why-tree claim resting on one input or none (a group counts once), a why-tree observation without a quote, an unrun test |

The why-tree follows the edges belief flows through, so the case and the computed beliefs agree. The data comes from `answer_cases` in `case.py`.

The answer is labelled, not highlighted:

- its node reads `CS1 · ANSWER` on the first label line, or `CS1 · ANSWER to G2` with several goals, in Mermaid and in the offline SVG
- its detail card and popup carry the same label beside the node type
- the focus dropdown lists it as `CS1 (ANSWER)`. Picking a candidate there highlights its derivation; nothing is focused by default

Candidates are ranked only under Rivals in the case. The belief of each claim is also on its node.

### Belief display

Claim nodes show `belief <value>` in both Mermaid and offline SVG, including nodes that inherit all their belief. This is the effective result used for candidate ranking, not the authored `score`. Goals, constraints, and tests have no belief label.

Node details separate **Effective belief** from **Score**, which shows only when authored. For example, premise `0.7` and score 5 give a graph label `belief 63%` and details `Score: 5`. Every belief on the page is a whole percent, so claims compare at a glance; the ends read `>99%` and `<1%`, since no belief is certain. Rendering never writes these computed values into the state.

When the answer names a candidate that another candidate of the same goal outranks, the report says so under the answer: `Answer CS2 is not the top-ranked candidate for G1: CS1 ranks higher`. Only the reader is told; `audit` accepts any grounded candidate as the answer.

Canvas rules:

- A curated explanation graph is optional. Use it when the full graph is too dense for the main story; aim for 8-18 nodes and rarely more than 25. If the full graph is already small/readable, it can serve as the explanation view.
- Full audit graph is complete and may be dense; put it in a canvas with pan/zoom instead of shrinking it until unreadable. Use subgraph grouping by node type when it improves relationship readability. Add edge interaction when possible: hover previews connected nodes, click pins the edge + endpoints, and Escape/blank-canvas click clears the pin.
- The graph is laid out left to right, so the observations, the widest rank of a real graph, stack in a column instead of one row wider than any screen. The canvas opens with the graph fitted to its width, never above natural size, and grows as tall as that takes, up to two screens; past that the graph fits the capped height. The page scroll still passes over the canvas, so a tall canvas reads like a tall figure. The offline SVG moves an edge label down until it clears the labels placed before it.
- The canvas view is fitted to the graph, then wheel zoom stays between the fitted view and a 50x zoom-in. Drag panning is unbounded, so the graph can be dragged off the canvas like a document can be scrolled away; every canvas keeps a "Reset view" control that restores the fit. The canvas clips at its own edges, which is why the graph must fill the canvas box rather than sit in a short strip: Mermaid renders inside its own `pre.mermaid` wrapper, so that wrapper carries the canvas height.
- Wheel zoom is opt-in per canvas: the canvas must hold focus (click it or Tab into it) before the wheel zooms, otherwise the wheel keeps scrolling the page normally. The focused canvas is outlined and sits on a dotted sheet background so it is obvious which surface owns the scroll.
- Keep graph labels to ID/type plus effective belief on claims; keep full text and authored inputs in node-detail cards/modals.
- Use `short_text` only for small bespoke presentation graphs where the label is clearly readable and does not risk escaping/entity noise.
- Prefer click-to-details anchors over huge node labels.
- Mermaid supports node click links with tooltips, e.g. `click E15 "#details-E15" "Full detail"`; default UX should intercept clicks and open a popup/modal card so the user stays near the canvas. Keep anchor targets as no-JS fallback.
- If using Mermaid click links/callbacks, initialize with `securityLevel: "loose"` when needed.
- Do not expose only a dense full graph in a bespoke report. For nontrivial graphs, include a readable explanation view such as a curated graph or a candidate-focused summary.
- Avoid forcing scroll for normal node inspection. Prefer popup/modal detail cards.

Mermaid styling pattern:

```mermaid
flowchart TD
  O1["observation: input is sorted"] --> H2["hypothesis: two-pointer is viable"]
  C1["constraint: O(n) time"] --> H2
  H1["H1<br/>hypothesis<br/>belief 0.5"] --> CS1["CS1<br/>candidate<br/>belief 0.5"]
  CS1 -- answers --> G
  O2["observation: violates O(n)"] -. contradicts .-> H1

  classDef candidate fill:#dbeafe,stroke:#2563eb;
  classDef bad fill:#fee2e2,stroke:#dc2626;

  class CS1 candidate;
  class O2 bad;
```

HTML report design guidance:

- Avoid rigid, generic templates. Make the report serve the reasoning object.
- Put the answer before the graph so users know what they are looking at.
- Use a small explanation view for the main story when the full graph is dense; use the full audit graph as an inspectable canvas.
- Keep graph labels compact using the belief display above; route observation text to filterable detail cards and modal popups.
- Do not add a separate observations/constraints section if the node details list already covers observations and constraints with sources.
- Use `reasoning-graph html --spacing relaxed|wide|compact|default` when dense graphs look compressed; compare against default spacing first.
- Use `reasoning-graph html --offline` when generated HTML must not require network access. Keep Mermaid source as source/fallback text in offline mode, not as a CDN runtime dependency.
- If using a full SVG graph fallback, add pan/zoom controls or viewBox-based pointer navigation.
