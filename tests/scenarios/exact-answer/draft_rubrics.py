"""Draft a scorer rubric for each item the pilot kept (issue #37).

    uv run tests/scenarios/exact-answer/draft_rubrics.py <items-root> [--model <model-id>]

items-root is one source dir, e.g. test-results/exact-answer/true-detective.
Reads <items-root>/pilot-selection.json from score_pilot.py. For every kept item it reads
problem.md and the solution text in gold.json, and writes rubric.json beside them:

    {"answer": "b", "key_points": [{"id": "K1", "point": "...", "hint": "..."}, ...]}

The loop driver sends the hint of the first key point a submit fails, so key points run
from the least revealing to the decisive one. An item that already has a rubric.json is
skipped: a rubric is checked by hand after drafting, and a rerun must not undo that.
rubric.json is a spoiler, like gold.json: keep it out of git and out of agent workspaces.
"""

import argparse
import json
import re
from pathlib import Path

from model_call import structured_call

DEFAULT_MODEL = "claude-opus-5-5"
# With room for four, every drafted rubric came back with four: the drafter pads.
MIN_KEY_POINTS = 1
MAX_KEY_POINTS = 3
MAX_DRAFT_ATTEMPTS = 3
# Words of an answer option that many suspects share, so they do not give the answer away.
SHARED_OPTION_WORDS = {"The", "Mr", "Mrs", "Ms", "Miss", "Dr", "Private", "First", "Class", "Specialist",
                       "Fourth", "Fifth", "Sergeant", "Officer", "Captain", "Professor"}

RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "key_points": {
            "type": "array",
            "minItems": MIN_KEY_POINTS,
            "maxItems": MAX_KEY_POINTS,
            "items": {
                "type": "object",
                "properties": {"point": {"type": "string"}, "hint": {"type": "string"}},
                "required": ["point", "hint"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["key_points"],
    "additionalProperties": False,
}

DRAFT_PROMPT = """Below are a detective puzzle, its answer options, the correct answer, and the author's solution.

Write a rubric for grading a solver's written reasoning.

Key points ({min_points} to {max_points}):
- Each key point is a conclusion the correct solution cannot do without. Leave out a point a
  solver could skip and still solve the puzzle soundly.
- Each holds exactly one conclusion, in one short sentence. Do not chain a conclusion to its
  supporting details: a grader has to answer "does the solver conclude this?" with yes or no.
- Each must be derivable from the puzzle text alone. Leave out anything that appears only in the
  solution, such as a confession.
- Clearing a rival suspect is a key point only when the solution gives a decisive reason for it.
- Order them from the least revealing to the decisive one.

Hints (one per key point):
- A hint tells the solver where to look again. It names a statement, an object, a time, or a
  detail of the puzzle to re-examine.
- A hint never gives the answer letter and never states the conclusion of its key point.
- A hint never names the correct answer. No hint may contain any of these words: {banned_words}.

# Puzzle

{problem}

# Correct answer

({answer}) {answer_option}

# Author's solution

{solution}
"""


def answer_option(problem: str, letter: str) -> str:
    """The text of one answer option, e.g. "Private Joe Locke" for letter b."""
    return re.search(rf"^- \({letter}\) (.+)$", problem, re.MULTILINE).group(1).strip()


def hints_naming_answer(key_points: list[dict], banned_words: list[str]) -> list[str]:
    # Case matters: the option "April Key" must not ban every hint about a keyboard key.
    return [key_point["hint"] for key_point in key_points
            if any(re.search(rf"\b{re.escape(word)}\b", key_point["hint"]) for word in banned_words)]


def draft_rubric(item_dir: Path, model: str) -> dict:
    gold = json.loads((item_dir / "gold.json").read_text(encoding="utf-8"))
    problem = (item_dir / "problem.md").read_text(encoding="utf-8")
    option = answer_option(problem, gold["answer"])
    banned_words = [word for word in re.findall(r"[A-Za-z]+", option) if word not in SHARED_OPTION_WORDS]
    prompt = DRAFT_PROMPT.format(
        min_points=MIN_KEY_POINTS, max_points=MAX_KEY_POINTS, problem=problem,
        answer=gold["answer"], answer_option=option, banned_words=", ".join(banned_words),
        solution=gold["solution"],
    )
    for _ in range(MAX_DRAFT_ATTEMPTS):
        drafted = structured_call(prompt, RUBRIC_SCHEMA, model)
        if not hints_naming_answer(drafted["key_points"], banned_words):
            break
    else:
        raise ValueError(f"{item_dir.name}: every draft had a hint naming the answer ({option})")
    key_points = [{"id": f"K{index}", **key_point}
                  for index, key_point in enumerate(drafted["key_points"], start=1)]
    return {"answer": gold["answer"], "key_points": key_points}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("items_root", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    selection = json.loads((args.items_root / "pilot-selection.json").read_text(encoding="utf-8"))
    for result in selection:
        if result["decision"] != "keep":
            continue
        item_dir = args.items_root / result["item"].split("/")[-1]
        rubric_file = item_dir / "rubric.json"
        if rubric_file.exists():
            print(f"skip   {result['item']} (rubric exists)")
            continue
        rubric = draft_rubric(item_dir, args.model)
        rubric_file.write_text(json.dumps(rubric, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"draft  {result['item']} ({len(rubric['key_points'])} key points)")


if __name__ == "__main__":
    main()
