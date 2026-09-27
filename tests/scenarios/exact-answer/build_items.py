"""Sample exact-answer benchmark items into problem packets (issue #34).

    uv run tests/scenarios/exact-answer/build_items.py \
        --true-detective <detective-puzzles.csv> --boardgame-qa <bbeh_boardgame_qa/task.json> \
        --per-source 20 --out test-results/exact-answer

Writes <out>/<source>/<item-id>/problem.md and gold.json. bench.sh copies only
problem.md into the agent workspace, so the gold answer never reaches the agent.
True Detective is licensed for academic research only: keep the output out of git.
"""

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

SAMPLE_SEED = 34

# Both arms get the same answer contract, so exact-match scoring needs no LLM judge.
ANSWER_CONTRACT = """## Required answer format

End `answer.md` with exactly one line:

    FINAL ANSWER: {answer_slot}

Give your best single answer even if you are unsure; put any doubts above that line.
"""

# Instruction wording follows the True Detective paper's default prompt.
TRUE_DETECTIVE_TEMPLATE = """# {case_name}

Your task is to solve a given mystery. The mystery is a detective puzzle presented
as a short story. Only one answer option is correct; identify which one.

## Mystery

{mystery_text}

## Answer options

{answer_options}

""" + ANSWER_CONTRACT

BOARDGAME_QA_TEMPLATE = """# BoardgameQA item

{question}

""" + ANSWER_CONTRACT


def option_letter(option_text: str) -> str:
    match = re.match(r"\s*\(([a-z])\)", option_text)
    if not match:
        raise ValueError(f"option without a (letter) prefix: {option_text!r}")
    return match.group(1)


def true_detective_items(csv_path: Path) -> list[dict]:
    csv.field_size_limit(10**9)
    items = []
    for row in csv.DictReader(csv_path.open(encoding="utf-8")):
        options = row["answer_options"].split("; ")
        letters = [option_letter(option) for option in options]
        items.append({
            "id": row["case_url"].rstrip("/").rsplit("/", 1)[-1],
            "problem": TRUE_DETECTIVE_TEMPLATE.format(
                case_name=row["case_name"],
                mystery_text=row["mystery_text"].strip(),
                answer_options="\n".join(f"- {option}" for option in options),
                answer_slot=f"<one letter: {', '.join(letters)}>",
            ),
            "gold": {"answer": option_letter(row["answer"]), "choices": letters,
                     "human_solve_rate": float(row["solve_rate"])},
        })
    return items


def boardgame_qa_items(task_path: Path) -> list[dict]:
    examples = json.loads(task_path.read_text(encoding="utf-8"))["examples"]
    choices = ["proved", "disproved", "unknown"]
    return [{
        "id": f"bgqa-{index:03d}",
        "problem": BOARDGAME_QA_TEMPLATE.format(
            question=example["input"].strip(), answer_slot="<proved | disproved | unknown>"),
        "gold": {"answer": example["target"], "choices": choices},
    } for index, example in enumerate(examples)]


def stratified_sample(items: list[dict], count: int, rng: random.Random) -> list[dict]:
    """Sample round-robin across gold labels so no answer label dominates."""
    by_label = defaultdict(list)
    for item in items:
        by_label[item["gold"]["answer"]].append(item)
    pools = [rng.sample(pool, len(pool)) for _, pool in sorted(by_label.items())]
    sample = []
    while len(sample) < count:
        for pool in pools:
            if pool and len(sample) < count:
                sample.append(pool.pop())
    return sample


def write_items(out_dir: Path, source: str, items: list[dict]) -> None:
    for item in items:
        item_dir = out_dir / source / item["id"]
        item_dir.mkdir(parents=True, exist_ok=True)
        (item_dir / "problem.md").write_text(item["problem"], encoding="utf-8")
        (item_dir / "gold.json").write_text(json.dumps(item["gold"], indent=2) + "\n", encoding="utf-8")
    print(f"{source}: {len(items)} items -> {out_dir / source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--true-detective", type=Path, required=True)
    parser.add_argument("--boardgame-qa", type=Path, required=True)
    parser.add_argument("--per-source", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rng = random.Random(SAMPLE_SEED)
    # True Detective answers are option letters whose count varies per case, so a plain sample.
    write_items(args.out, "true-detective", rng.sample(true_detective_items(args.true_detective), args.per_source))
    write_items(args.out, "boardgame-qa", stratified_sample(boardgame_qa_items(args.boardgame_qa), args.per_source, rng))


if __name__ == "__main__":
    main()
