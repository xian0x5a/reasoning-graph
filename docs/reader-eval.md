# Reader eval

Measures whether a record helps a reader check an answer (#39). The plan, with full tables and discoveries: `plans/done/reader-eval.md`.

## What it measures

Three views of a solved True Detective item, each read with the answer it explains:

- **page:** the case-first page of a graph run, as visible text.
- **transcript:** the same graph run's sessions as text. It holds the story, since the agent read it.
- **notes:** `notes.md` of a notes-file run.

Two tasks, each a single structured call to a model reader with no tools and no story:

- **Trace:** for each rubric key point, copy the story passage the view shows for it. It counts when the passage is verbatim in the view and the story and a judge holding the story says it is the point's clue.
- **Catch:** list up to five overclaims or wrong weights. Each view is read planted (one flaw per item, checked by hand against the story) and clean. A judge files each finding as the plant, a real flaw, or spurious.

Reading cost is the view's size in characters.

## Running it

Scripts live in `tests/scenarios/exact-answer/`. Outputs stay under the ignored `test-results/exact-answer/true-detective/<item>/reader/`, because the case texts are licensed for research only.

```sh
uv --project packages/reasoning-graph run python tests/scenarios/exact-answer/reader_views.py <item-dir>...
uv run tests/scenarios/exact-answer/draft_plants.py <item-dir>...     # then check each plants.json by hand
uv --project packages/reasoning-graph run python tests/scenarios/exact-answer/reader_views.py <item-dir>...  # writes views/planted/
uv run tests/scenarios/exact-answer/run_reader.py trace <item-dir>... --repeats 3
uv run tests/scenarios/exact-answer/run_reader.py catch <item-dir>... --repeats 3
uv run tests/scenarios/exact-answer/score_reader.py <item-dir>... --by-item
```

`run_reader.py` skips reads that already have a result, so a rerun retries only the failed ones. The safety classifier refuses a few short notes reads; those are reported as missing.

## Result (`s55-loop-r1`, 11 items, 3 reads each)

| | page | transcript | notes |
| --- | --- | --- | --- |
| Reading size (chars) | 7.0k | 42.6k | 2.1k |
| Key points traced | 94/99 | 99/99 | 14/84 |
| Plants caught | 33/33 | 33/33 | 28/33 |
| Spurious findings | 139 | 93 | 236 |

- **The graph record beats a notes file for a reader.** Notes hold no quotes, so a reader can trace almost nothing and cries wolf most.
- **The page does not beat the transcript.** It matches catch at a sixth of the reading, but raises more spurious findings. The gap is in findings that argue with a quote (about 106 to 58; other spurious findings are about even): a node's text often draws on story the page does not quote, and the page's reader, holding no story, flags it. The transcript's reader can check the whole story. Source links give a human reader that story; the model reader here had none.
- **On the page, a quote gap outranks a wrong weight.** The planted weight was caught in all 15 page reads but ranked first in 4, against 9 of 15 on the transcript. What ranked above it was mostly quote-based (23 of 29 findings) and mostly real (17 of 29). Each quote sits beside its node's text, so a gap between them is the first thing a reader lists.
- Both tasks hit a ceiling on page and transcript, and n is 11. Differences show in rank and false alarms, not in hit rates.
