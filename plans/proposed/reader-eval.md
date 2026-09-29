# Reader eval

The measure half of #39. The case-first page exists (`plans/done/case-first-page.md`); this plan measures whether it lets a reader check the answer better than the alternatives.

## Goal

A number, per view, for two things a reader does when checking an answer:

- **Trace:** follow each point the answer rests on to the verbatim passage of the story it comes from.
- **Catch:** find a flaw planted in the reasoning, and not cry wolf on a record without one.

Plus how much the reader had to read to do it.

## Intention

#37 ended with the graph tying a plain notes file as memory: 12 of 14 passed each, the graph at 1.8× the cost. So the record has to earn that cost from the reader, and nothing shows yet that a reader gets anything from it.

Three findings from the `s55-loop-r1` material shape the design:

- `answer.md` already names the decisive clue (796–2858 bytes, and every passed answer covers all rubric key points). "Find the decisive evidence", given the answer, is a trivial task in every view. What the answer does not give is where each point comes from, so the task becomes tracing it to the story.
- The notes files are 237–4653 bytes and quote the story verbatim nowhere. Each graph run's transcript (81–296 KB) holds the whole story, because the agent read it.
- 139 of 144 graph quotes are verbatim substrings of the story, after whitespace and curly quotes are normalised. So a traced quote can be checked by substring, with no judge.

## Scope & Constraints

In scope:

- Three views of each item, each given to the reader together with the answer it explains:
  - **page:** the case-first page of the graph run, as visible text. Scripts, styles, the SVG and the Mermaid source are dropped. This measures the page's content and order, not its visuals.
  - **transcript:** the graph run's session transcripts as plain text: user and assistant turns, and tool results. It holds the same reasoning as the page, so page against transcript isolates the presentation.
  - **notes:** `notes.md` of the notes-file run, with that run's answer.
- The 11 items where both the graph run and the notes-file run of `s55-loop-r1` passed, at each run's last round. Excluded: the-anonymous-bank-robber, the-card-shark, the-golden-ruse.
- A model reader for the runs; an optional check by the user at the end.

Out of scope:

- Changing the page. If the eval shows a gap, that is a follow-up.
- The visual page: layout, canvas, popups. Only the optional human check sees it.

Constraints:

- True Detective texts, views, plants and reader outputs stay out of git, under `test-results/exact-answer/true-detective/<item>/reader/`. Scripts go under `tests/scenarios/exact-answer/`.
- The reader gets no tools and no story: one structured call per task with the answer and one view, through `model_call.structured_call`. The transcript view still holds the story. That is its real advantage, and it is reported, not removed.
- The reader is `claude-opus-5-5`, not the `claude-sonnet-5-5` that wrote the records, so it does not share the author's misreadings of a clue (#36 traced most wrong answers to a misread clue). The judge is `claude-opus-5-5` too; it only matches reader output against known keys.
- Pilot before the full run: 3 items end to end, then 11.

## Tasks

| Task | Reader is asked | Scored by |
| --- | --- | --- |
| Trace | For each point the answer rests on: the claim, and the verbatim story passage the view shows for it, or "not shown". | A quote counts when it is a normalised substring of the story (mechanical). A rubric key point counts as traced when the judge maps a claim with a verbatim quote to it. Hit rate is traced key points ÷ key points. |
| Catch | Where does the reasoning claim more than its source supports, or lean on evidence that does not bear on the answer? Name the place (node id, or the quoted line) and say why; or say none. | The judge sorts each finding: the planted flaw, a real flaw already in the record, or spurious. Real flaws are checked by hand before they count. Hit rate is planted flaws caught; false alarms are spurious findings, clean records included. |

Reading cost is the view's size in tokens, from the call's usage. For a single model call that is the whole of "time"; timing a reader in minutes is left to the human check.

## Plants

One plant per item and view, alternating between two kinds by item:

| Kind | page (edit the state, re-render) | transcript (edit an assistant turn) | notes (edit a line) |
| --- | --- | --- | --- |
| overclaim | an observation of the why-tree says more than its quote; the quote is unchanged | the agent states the same stronger fact | the note states the same stronger fact |
| wrong weight | an observation that does not bear on the answer `supports` it at score 5 | the agent calls that clue strong support | the note calls that clue strong support |

- The same fact is planted in every view that holds it. When the notes lack it, the notes get the same kind of plant on a fact they do hold, and the plant file records the swap.
- Each item-view is also read clean, as the control.
- A model drafts the plants from the story, the state and the notes (`draft_plants.py`). I check each by hand: the flaw is real against the story, and it is the only change.
- Planted states are re-rendered, so beliefs and weak spots move with the plant, as they would for a real flaw.

## Work Plan

1. **Views.** `reader_views.py <item>` writes `page.txt`, `transcript.txt`, `notes.txt` and the two answers under `<item>/reader/views/`. Checked by reading the three views of sweat-it-out.
2. **Trace.** `run_reader.py trace <item>...` reads, judges, and writes `<item>/reader/trace/<view>.json`. `score_reader.py` prints per view: hit rate, verbatim rate, reading tokens. Pilot on 3 items; read every reader output by hand.
3. **Plants.** `draft_plants.py` writes `<item>/reader/plants.json`; I check and fix all 11. `reader_views.py --plant` writes the planted views.
4. **Catch.** `run_reader.py catch <item>...` reads each planted and clean view, judges, and writes `<item>/reader/catch/<view>.<planted|clean>.json`. `score_reader.py` adds catch rate, false alarms, and real flaws found. Pilot on 3 items.
5. **Full run.** 11 items, each call 3 times, since a model reader varies. Results and the decision below go to #39 and to `docs/` as the accepted finding.
6. **Human check (optional, the user's call).** The user reads 4 items, timed: 2 on the rendered page in a browser, 2 on the transcript, with Catch only. A sanity check of the model result, not a statistic.

Commit after each step. Scripts only; outputs stay ignored.

## Decision rule

The page earns the record's cost from the reader when, on the full run:

- **Catch:** its hit rate beats notes and at least ties transcript, with no more false alarms than either.
- **Trace:** its hit rate beats notes and at least ties transcript, at under a quarter of the transcript's reading tokens.

If the page only ties notes on Catch, the record does not earn its cost from the reader. That answer goes back to #37.

Catch's two plant kinds give a first read on the open question of #39, whether the 1–5 score helps a reader catch a wrong weight: compare the page's hit rate on wrong-weight plants with its rate on overclaim plants. It is a hint, not a test; a real test would plant the same edge with and without its score.

## Validation

- The pilot's reader outputs are read by hand before the full run. A task the reader misunderstands shows there first.
- Every plant is checked by hand against the story before any Catch run.
- The verbatim check is tested on the graph quotes: 139 of 144 must pass, matching the count above.

## Risks

- **A clean record is not clean.** 5 graph quotes are not verbatim, and some records surely hold weak links. The judge files them as real flaws, and I check them, so a real catch is not scored as a false alarm.
- **Plants that give themselves away.** A planted sentence can read differently from the agent's own. The plant must match the voice of the record around it. I check this in step 3, and the clean control shows whether readers flag plants by style.
- **Small n.** 11 items, 3 reads each. A difference of one or two items is noise. The result is reported with per-item outcomes, not only rates.
- **Cost.** Transcripts run to about 75k tokens a call. The pilot reports its cost before the full run is started.

## Progress

- [ ] 1. Views
- [ ] 2. Trace
- [ ] 3. Plants
- [ ] 4. Catch
- [ ] 5. Full run
- [ ] 6. Human check

## Surprises & Discoveries

## Decisions

1. Trace replaces "find the decisive evidence": the answer already names it.
2. Page and transcript come from the same graph run, so the comparison isolates presentation. Notes come from the notes-file run, since that is the rival memory layer of #37.
3. The model reader reads the page as text. The visual page is for the human check.

## Outcomes & Retrospective
