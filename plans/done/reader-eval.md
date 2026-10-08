# Reader eval

The measure half of [removed link]. The case-first page exists (`plans/done/case-first-page.md`); this plan measures whether it lets a reader check the answer better than the alternatives.

## Goal

A number, per view, for two things a reader does when checking an answer:

- **Trace:** follow each point the answer rests on to the verbatim passage of the story it comes from.
- **Catch:** find a flaw planted in the reasoning, and not cry wolf on a record without one.

Plus how much the reader had to read to do it.

## Intention

[removed link] ended with the graph tying a plain notes file as memory: 12 of 14 passed each, the graph at 1.8× the cost. So the record has to earn that cost from the reader, and nothing shows yet that a reader gets anything from it.

Three findings from the `s55-loop-r1` material shape the design:

- `answer.md` already names the decisive clue (796–2858 bytes, and every passed answer covers all rubric key points). "Find the decisive evidence", given the answer, is a trivial task in every view. What the answer does not give is where each point comes from, so the task becomes tracing it to the story.
- The notes files are 237–4653 bytes and quote the story verbatim nowhere. Each graph run's transcript (81–296 KB) holds the whole story, because the agent read it.
- 139 of 144 graph quotes are verbatim substrings of the story, after whitespace and curly quotes are normalised. So a traced quote can be checked by substring, with no judge.

## Scope & Constraints

In scope:

- Three views of each item, each given to the reader together with the answer it explains:
  - **page:** the case-first page of the graph run, as visible text. Scripts, styles, the SVG and the Mermaid source are dropped. This measures the page's content and order, not its visuals.
  - **transcript:** the graph run's sessions as plain text: the agent's text, its tool calls and their results. It holds the same reasoning as the page, so page against transcript isolates the presentation. The skill text the harness injects and the grader's feedback turns are dropped; what the agent wrote down from the feedback stays, as it does in the other two views.
  - **notes:** `notes.md` of the notes-file run, with that run's answer.
- The 11 items where both the graph run and the notes-file run of `s55-loop-r1` passed, at each run's last round. Excluded: the-anonymous-bank-robber, the-card-shark, the-golden-ruse.
- A model reader for the runs; an optional check by the user at the end.

Out of scope:

- Changing the page. If the eval shows a gap, that is a follow-up.
- The visual page: layout, canvas, popups. Only the optional human check sees it.

Constraints:

- True Detective texts, views, plants and reader outputs stay out of git, under `test-results/exact-answer/true-detective/<item>/reader/`. Scripts go under `tests/scenarios/exact-answer/`.
- The reader gets no tools and no story: one structured call per task with the answer and one view, through `model_call.model_call`. The transcript view still holds the story. That is its real advantage, and it is reported, not removed.
- The reader is `claude-opus-5-5`, not the `claude-sonnet-5-5` that wrote the records, so it does not share the author's misreadings of a clue ([removed link] traced most wrong answers to a misread clue). The judge is `claude-opus-5-5` too; it only matches reader output against known keys.
- Pilot before the full run: 3 items end to end, then 11.

## Tasks

| Task | Reader is asked | Scored by |
| --- | --- | --- |
| Trace | For each rubric key point: the story passage the view shows for it, copied exactly, or nothing. | The passage must be in the view and in the story, by normalised substring (mechanical). A judge holding the story then says whether it is the point's clue. Hit rate is traced key points ÷ key points. |
| Catch | Up to five overclaims or wrong weights, most serious first: the place (node id, or an excerpt) and why; or none. | The judge sorts each finding: the planted flaw, a real flaw already in the record, or spurious. Real flaws are checked by hand before they count. Hit rate is planted flaws caught; false alarms are spurious findings, clean records included. |

Reading cost is the view's size in characters. A call's token count does not measure it: the harness adds about 7k tokens of its own to every call. For a single model call, size is the whole of "time"; timing a reader in minutes is left to the human check.

## Plants

One plant per item and view, alternating between two kinds by item:

| Kind | page (edit the state, re-render) | transcript (exact text edits) | notes (exact text edits) |
| --- | --- | --- | --- |
| overclaim | an observation of the why-tree says more than its quote; the quote is unchanged | the node's text, wherever it appears, says the same | the note states the same stronger fact |
| wrong weight | an observation that does not bear on the answer `supports` it, or a why-tree hypothesis, at score 5 | a sentence in the agent's last session calls that clue strong support | a line calls that clue strong support |

- The same fact is planted in every view that holds it. When the notes lack it, the notes get the same kind of plant on a fact they do hold, and the plant file records the swap.
- Each item-view is also read clean, as the control.
- A model drafts the plants from the story and the three views (`draft_plants.py`). I check each by hand: the flaw is real against the story, and it is the only change.
- Planted states are re-rendered, so beliefs and weak spots move with the plant, as they would for a real flaw.

## Work Plan

1. **Views.** `reader_views.py <item>` writes `page.txt`, `transcript.txt`, `notes.txt` and the two answers under `<item>/reader/views/`. Checked by reading the three views of sweat-it-out.
2. **Trace.** `run_reader.py trace <item>...` reads, judges, and writes `<item>/reader/trace/<view>.json`. `score_reader.py` prints per view: hit rate, verbatim rate, reading tokens. Pilot on 3 items; read every reader output by hand.
3. **Plants.** `draft_plants.py` writes `<item>/reader/plants.json`; I check and fix all 11. `reader_views.py` then writes the planted views as well.
4. **Catch.** `run_reader.py catch <item>...` reads each planted and clean view, judges, and writes `<item>/reader/catch/<view>.<planted|clean>.json`. `score_reader.py` adds catch rate, false alarms, and real flaws found. Pilot on 3 items.
5. **Full run.** 11 items, each call 3 times, since a model reader varies. Results and the decision below go to [removed link] and to `docs/` as the accepted finding.
6. **Human check (optional, the user's call).** The user reads 4 items, timed: 2 on the rendered page in a browser, 2 on the transcript, with Catch only. A sanity check of the model result, not a statistic.

Commit after each step. Scripts only; outputs stay ignored.

## Decision rule

The page earns the record's cost from the reader when, on the full run:

- **Catch:** its hit rate beats notes and at least ties transcript, with no more false alarms than either.
- **Trace:** its hit rate beats notes and at least ties transcript, at under a quarter of the transcript's reading size.

If the page only ties notes on Catch, the record does not earn its cost from the reader. That answer goes back to [removed link].

Catch's two plant kinds give a first read on the open question of [removed link], whether the 1–5 score helps a reader catch a wrong weight: compare the page's hit rate on wrong-weight plants with its rate on overclaim plants. It is a hint, not a test; a real test would plant the same edge with and without its score.

## Validation

- The pilot's reader outputs are read by hand before the full run. A task the reader misunderstands shows there first.
- Every plant is checked by hand against the story before any Catch run.
- The verbatim check is tested on the graph quotes: 141 of 144 pass. It also reads an ellipsis as a gap and ignores end punctuation, which accounts for the gain on the count above; the three misses quote the grader, not the story.

## Risks

- **A clean record is not clean.** 5 graph quotes are not verbatim, and some records surely hold weak links. The judge files them as real flaws, and I check them, so a real catch is not scored as a false alarm.
- **Plants that give themselves away.** A planted sentence can read differently from the agent's own. The plant must match the voice of the record around it. I check this in step 3, and the clean control shows whether readers flag plants by style.
- **Small n.** 11 items, 3 reads each. A difference of one or two items is noise. The result is reported with per-item outcomes, not only rates.
- **Cost.** Transcripts run to about 75k tokens a call. The pilot reports its cost before the full run is started.

## Progress

- [x] 1. Views (0b89043)
- [x] 2. Trace (4dcda24; pilot on 3 items, read by hand)
- [x] 3. Plants (e6baa8d; 11 drafted, all checked by hand, one written by hand)
- [x] 4. Catch (pilot on 3 items, read by hand; then 97e89ae, dffbaf2 for refusals)
- [x] 5. Full run (11 items × 3 repeats: 99 trace reads, 198 catch reads)
- [x] 6. Human check: skipped, the user's call. A 4-item pack was built with source links; the user looked it over and did not run it.

## Surprises & Discoveries

- **The `s55` final states predate the current schema.** They carry edge ids, `stop_policy` and `events`, so the page reported "43 checks fail". `reader_views.py` drops those fields before rendering; the audit then passes.
- **4 of 11 graph agents never set `summary.answer`,** although each passed with a lettered answer. Their pages would open with no case, so the views fill it from the passed answer's letter (`UNCLAIMED_ANSWERS`). The skill lets an agent finish without claiming its answer in the state; that is a gap of its own, not this eval's.
- **The grader's hints sit inside both memories.** The graph records them as `GRADER FEEDBACK` observations, the notes as feedback sections. Every view shows them, so no view gets an edge from them.
- **As text, the transcript is small.** The raw jsonl is 81–296 KB; the text the agent saw and wrote is 16–58k characters. The page is about 1/6 of that (4.8–9.2k), the notes 0.2–4.7k.
- **Trace has a ceiling.** In the pilot, page and transcript traced 9 of 9 key points, notes 1 of 9. A reader of the page or the transcript almost always finds the quote, since both carry the verbatim passage for every point. Trace separates notes from the graph, not page from transcript.
- **The safety classifier refuses some reads.** A refused call exits 1 with `stop_reason: refusal`. The reader of mystery-of-the-bratty-kid's notes is refused on every try (a 7-year-old in a story about a smashed gift); other refusals are sporadic and pass on a rerun. The plant drafter was refused on the-cocktail-conundrum (a poisoning), so that plant is written by hand.
- **A planted edge shows its score.** The page prints `score 5` on a scored edge, and most records score few edges, so a planted wrong weight can stand out by its score alone. That is the feature under test, not a leak: a real wrong weight would show it too.

## Decisions

1. Trace replaces "find the decisive evidence": the answer already names it.
2. Page and transcript come from the same graph run, so the comparison isolates presentation. Notes come from the notes-file run, since that is the rival memory layer of [removed link].
3. The model reader reads the page as text. The visual page is for the human check.
4. Reading cost is the view's size in characters, not tokens: every harness call adds about 7k tokens of its own.
5. Plants where a clue that clears one suspect is made strong support for the answer (dead-mans-island, the-secret-in-the-old-trunk) are kept. Clearing one suspect of several is weak support at most, so a score 5 is a real overweight, but it is the mildest wrong weight in the set.
6. A read the classifier refuses is reported as missing, not scored as a miss, and the counts show it.
7. The reader's system prompt says the puzzle is published fiction. Without it the classifier refused three items' notes reads every time; with it, two still are (cocktail 3 of 3, trunk 2 of 3), 5 of 99 trace reads. No catch read was refused. The first trace run and the catch pilot, read under the old prompt, were discarded and rerun.

## Outcomes & Retrospective

Full run, 11 items × 3 reads, reader and judge `claude-opus-5-5`. Reproduce with `score_reader.py <item-dirs> --by-item`.

| | page | transcript | notes |
| --- | --- | --- | --- |
| Reading size (chars, mean) | 7.0k | 42.6k | 2.1k |
| Trace: key points traced | 94/99 | 99/99 | 14/84 |
| Catch: plants caught | 33/33 | 33/33 | 28/33 |
| Catch: plant ranked first | 16/33 | 20/33 | 22/33 |
| Real flaws found, planted/clean | 78/76 | 91/113 | 22/42 |
| Spurious findings, planted/clean | 54/85 | 41/52 | 114/122 |
| Cost (trace + catch) | $15.20 | $29.67 | $12.47 |

By plant kind, where the plant ranks among the five findings:

| | overclaim first | overclaim rank | wrong weight first | wrong weight rank |
| --- | --- | --- | --- | --- |
| page | 12/18 | 1.7 | 4/15 | 2.9 |
| transcript | 11/18 | 1.6 | 9/15 | 1.7 |
| notes | 7/18 (13 caught) | 1.8 | 15/15 | 1.0 |

**Against the decision rule:**

- Against notes, the page wins on everything: it traces 95% of key points to 17%, catches every plant to 85%, finds 2.4× the real flaws and raises 40% fewer spurious ones. The graph record earns its cost from the reader over a notes file, which is the question [removed link] left.
- Against the transcript, the page does not meet the rule. It ties on catch rate but raises more spurious findings (139 to 93), and traces 94 to 99. It does that at a sixth of the reading. The transcript's edge is the story it holds: its reader checks a quote against the text, so its doubts are real flaws, not guesses. The spurious gap is all in findings that argue with a quote (about 106 to 58, by keyword; the rest are about even): a node's text often draws on story the page does not quote.
- **On the page, a quote gap outranks a wrong weight.** The page shows `score 5` on the planted edge and every read caught it, but it ranked first in 4 of 15. Findings above it were 17 real and 12 spurious, and 23 of the 29 argue with a quote: each quote sits beside its node's text, so a gap between them is what a reader lists first. On the transcript only real flaws outranked it. Whether the score helps stays open: the transcript and notes plants are a sentence that says "strong support" out loud, which stands out more than an edge in a tree.

**What the numbers do not say:**

- Both tasks hit a ceiling on page and transcript: every plant is caught, nearly every key point traced. Rank and false alarms carry the differences, and they rest on 11 items.
- Readers return five findings on every read, clean records included. "Spurious" measures what a reader fills the slots with when the view does not let it check, more than a tendency to cry wolf.
- Clean records are not clean: 231 findings on clean reads are real flaws by the judge. A sample of 8 read by hand holds up (two checked against the story: a quote that is a rhetorical question, and one that breaks off mid-sentence).

**Follow-ups, not in this plan:**

- The page could show enough of the story around each quote for a reader to check it, which is the transcript's one advantage.
- A wrong-weight test that plants the same edge with and without its score, as [removed link] asks.
- The skill lets an agent finish without setting `summary.answer` (4 of 11 here).

Spent: $57.34 on the reads that count, about $15 on the discarded first trace run and pilot, plus the plant drafts (not logged).
