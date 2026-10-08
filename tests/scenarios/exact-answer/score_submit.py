"""Grade one submit of the resume loop against an item's rubric.

    uv run tests/scenarios/exact-answer/score_submit.py <item-dir> <answer.md> [--repeat 3] [--model <model-id>]

The answer letter is graded by exact match, so a wrong letter never passes. A model grades
only the reasoning: for each key point of rubric.json it quotes the sentence that covers it,
or quotes nothing. A key point counts as covered only when that quote is found in the submit,
which keeps the scorer from crediting a point the solver never wrote.
It never writes a hint; the loop driver sends the hint the rubric already holds.
--repeat grades the same submit several times and reports whether the verdicts agree, to
check the scorer before an arm is run.
"""

import argparse
import json
import re
from pathlib import Path

from model_call import structured_call
from score_pilot import FINAL_ANSWER_PATTERN

# Sonnet 5.5 gave different verdicts on repeats of the same submit; Opus 5.5 gave the same five times.
DEFAULT_MODEL = "claude-opus-5-5"
COVERED = "covered"
MISSING = "missing"

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

SCORE_PROMPT = """Grade a solver's written reasoning about a detective puzzle against the key points below.

A key point holds a conclusion and the clue it rests on. For every key point, find the one
sentence or bullet of the reasoning that reaches the same conclusion from the same clue, and
copy it character for character into `quote`. Leave `quote` empty when the reasoning:
- reaches the conclusion by another route, without that clue,
- mentions the clue without drawing the conclusion from it,
- states the conclusion only as a doubt, or argues against it, or
- says nothing on the point.

The solver's wording may differ from the key point. A right final answer earns no credit for
a point the reasoning leaves out.

# Puzzle

{problem}

# Key points

{key_points}

# Solver's reasoning

{reasoning}
"""


def submitted_letter(answer_text: str, choices: list[str]) -> str | None:
    """The last FINAL ANSWER letter, or None when missing or not one of the choices."""
    matches = FINAL_ANSWER_PATTERN.findall(answer_text)
    letter = matches[-1].lower() if matches else None
    return letter if letter in choices else None


def normalized(text: str) -> str:
    """Text without Markdown emphasis, list marks, or spacing differences, for the quote check."""
    return re.sub(r"[\s*_`>#-]+", " ", text).strip().lower()


def key_point_verdicts(rubric: dict, problem: str, answer_text: str, model: str) -> dict[str, str]:
    prompt = SCORE_PROMPT.format(
        problem=problem,
        key_points="\n".join(f"- {key_point['id']}: {key_point['point']}" for key_point in rubric["key_points"]),
        reasoning=answer_text,
    )
    graded = structured_call(prompt, VERDICT_SCHEMA, model)
    submit_text = normalized(answer_text)
    verdicts = {entry["id"]: COVERED if entry["quote"].strip() and normalized(entry["quote"]) in submit_text
                else MISSING for entry in graded["verdicts"]}
    expected_ids = [key_point["id"] for key_point in rubric["key_points"]]
    if sorted(verdicts) != sorted(expected_ids):
        raise ValueError(f"scorer graded {sorted(verdicts)}, rubric has {expected_ids}")
    return verdicts


def score_submit(item_dir: Path, answer_text: str, model: str) -> dict:
    """Grade a submit. `first_failed` is the first key point not covered, whose hint goes out next."""
    gold = json.loads((item_dir / "gold.json").read_text(encoding="utf-8"))
    rubric = json.loads((item_dir / "rubric.json").read_text(encoding="utf-8"))
    problem = (item_dir / "problem.md").read_text(encoding="utf-8")
    letter = submitted_letter(answer_text, gold["choices"])
    verdicts = key_point_verdicts(rubric, problem, answer_text, model)
    failed = [key_point["id"] for key_point in rubric["key_points"] if verdicts[key_point["id"]] != COVERED]
    letter_correct = letter == gold["answer"]
    return {
        "letter": letter,
        "letter_correct": letter_correct,
        "verdicts": verdicts,
        "first_failed": failed[0] if failed else None,
        "passed": letter_correct and not failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item_dir", type=Path)
    parser.add_argument("answer_file", type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    answer_text = args.answer_file.read_text(encoding="utf-8")
    scores = [score_submit(args.item_dir, answer_text, args.model) for _ in range(args.repeat)]
    for score in scores:
        print(json.dumps(score))
    if args.repeat > 1:
        stable = all(score["verdicts"] == scores[0]["verdicts"] for score in scores)
        print("stable" if stable else "UNSTABLE: verdicts differ between repeats")


if __name__ == "__main__":
    main()
