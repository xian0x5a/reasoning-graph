# SPOILER Validator — Sea Shanty

Do not give this file to blind solvers before running the test.

## Expected final answer

Normalized final phrase:

```text
HOW NOT TO BULB
```

Accept case-insensitive variants with punctuation/spacing differences if the phrase is clearly this answer.

## Source confidence note

The Gold Bug puzzle page does not publish a solution on the page itself. This validator uses the answer Theo referenced while discussing Sea Shanty in the video “gpt-5.4 is really, really good” around 28:37–28:44. If an official Gold Bug solution later becomes available and differs, update this validator.

Relevant public sources:

- Puzzle page: https://goldbug.cryptovillage.org/puzzles/2025/Sea%20Shanty/
- Puzzle index: https://goldbug.cryptovillage.org/puzzles.html
- Theo video section: https://www.youtube.com/watch?v=HD5TWE8xD7o&t=1658s

## Expected solving behavior

A strong answer should treat the shanty as procedural cipher instructions, not flavor text.

Core expected moves:

1. Extract the 12 rum-bottle labels accurately from the image.
2. Notice the bottles are numbered 12 down to 1 and the shanty repeats from twelve bottles down to one bottle.
3. Interpret the repeated stanza as an iterative route/cipher procedure.
4. Use the instruction words as operations, especially:
   - “three swigs ahead” — a three-step/shift/counting operation.
   - “four cups aligned” — a four-column/four-position layout or alignment.
   - “starboard round” — rightward/clockwise rotation.
   - “slumped upon the table flat” — flatten/read out after rotation or laying down.
   - “on th'twelfth/eleventh/... cup” — take the selected position at each iteration.
5. Produce one extracted character per bottle/round and assemble the phrase.

The exact mechanical reconstruction may vary. Award high process credit if the solver gives a reproducible table/script or a clear enough hand table that yields `HOW NOT TO BULB` from the provided labels and shanty.

## Scoring rubric

Total: 100 points.

- Final answer: 35
  - 35: gives `HOW NOT TO BULB`.
  - 20: near miss with most words/letters correct.
  - 0–10: unrelated phrase.
- Evidence extraction: 15
  - Correctly transcribes bottle labels and recognizes 12 rounds.
  - Handles OCR ambiguity around `Iron Squalq Select` without derailing.
- Cipher/procedure reasoning: 30
  - Treats shanty lines as operations.
  - Uses the 3-step, 4-alignment, right-rotation, flattening, and iterative cup selection ideas.
  - Gives reproducible extraction rather than answer-only guess.
- Alternative handling: 10
  - Discusses plausible but losing paths: pure acrostic, simple Caesar on label text, reading bottle labels directly, image-description-only answer.
- Verification discipline: 10
  - Proposes re-running the extraction in a table/script or independently checking OCR/image labels.
  - Does not rely on Theo commentary, web search, or memorized answer during blind solving.

## Expected competing interpretations and why they lose

### Pure acrostic of label initials

Reasonable first try because the labels are prominent. Loses because initial strings do not yield a coherent phrase without using the shanty operations.

### Simple Caesar/ROT only

Reasonable because “three swigs ahead” suggests a shift. Loses because a shift alone does not explain the repeated countdown, four cups, starboard rotation, or one-character-per-round extraction.

### Read the bottle numbers directly

Reasonable because labels are numbered 12 to 1. Loses because the numbers are part of the iterative procedure, not the answer.

### Narrative answer about pirates/treasure

Weak. The puzzle explicitly asks for a hidden clue/phrase and provides procedural language.

## Graph review expectations

For a `reasoning-graph` run, good state should include:

- Facts for source page text, the 12 labels, and the shanty instructions.
- Candidate solutions for at least acrostic, Caesar/ROT, route/rotation procedure, and narrative/flavor interpretations.
- Proposed/performed tests that are concrete: acrostic extraction, Caesar shift test, four-column rotation test, and full iterative reconstruction.
- Final candidate ranked by reproducible extraction, not by answer plausibility alone.

## Common failure modes

- Searching web/video and answer-contaminating the run.
- Treating `HOW NOT TO BULB` as valid without explaining how the puzzle gives it.
- Hallucinating extra bottle labels not visible in the image.
- Ignoring the countdown from 12 to 1.
- Ignoring the words “three”, “four”, and “starboard”.
