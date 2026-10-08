"""Score the no-skill pilot by exact match and pick items for the A/B.

    uv run tests/scenarios/exact-answer/score_pilot.py <items-root> <run-id>...

items-root is test-results/exact-answer or one source dir under it.

Keep rule, fixed before the A/B: keep an item when at least one pilot run is wrong, and
the A/B uses every kept item.
McNemar's test ignores items both arms get wrong, so an always-wrong item costs runs but
adds no bias, and it is where the skill has the most room to help. Repeating the same wrong
answer is not evidence of a bad gold label: a hand check of such an item found a fair
puzzle and a real reasoning error. A run with no parseable answer is neither right nor
wrong: rerun it first.
"""

import argparse
import json
import re
from pathlib import Path

PILOT_ARM = "no-skill"
FINAL_ANSWER_PATTERN = re.compile(r"^\W*FINAL ANSWER\W*:\W*\(?([A-Za-z]+)\)?", re.MULTILINE)


def final_answer(run_dir: Path, choices: list[str]) -> str | None:
    """The last FINAL ANSWER line, or None when missing or not one of the choices."""
    answer_file = run_dir / "answer.md"
    if not answer_file.is_file():
        return None
    matches = FINAL_ANSWER_PATTERN.findall(answer_file.read_text(encoding="utf-8"))
    answer = matches[-1].lower() if matches else None
    return answer if answer in choices else None


def run_cost(run_dir: Path) -> float:
    """Claude Code reports the run total in its final stream-json event; pi logs cost per message."""
    transcript = run_dir / "transcript.jsonl"
    if transcript.is_file():
        events = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line]
        return sum(event.get("total_cost_usd", 0.0) for event in events if event.get("type") == "result")
    total = 0.0
    for session_file in (run_dir / "session").glob("**/*.jsonl"):
        for line in session_file.read_text(encoding="utf-8").splitlines():
            message = json.loads(line).get("message")
            if isinstance(message, dict) and "cost" in (message.get("usage") or {}):
                total += message["usage"]["cost"]["total"]
    return total


def score_item(item_dir: Path, run_ids: list[str]) -> dict:
    gold = json.loads((item_dir / "gold.json").read_text(encoding="utf-8"))
    run_dirs = [item_dir / PILOT_ARM / run_id for run_id in run_ids]
    answers = [final_answer(run_dir, gold["choices"]) for run_dir in run_dirs]
    wrong_answers = [answer for answer in answers if answer is not None and answer != gold["answer"]]
    if None in answers:
        decision = "rerun"
    elif not wrong_answers:
        decision = "drop"
    else:
        decision = "keep"
    return {
        "item": f"{item_dir.parent.name}/{item_dir.name}",
        "gold": gold["answer"],
        "answers": answers,
        "correct": answers.count(gold["answer"]),
        "wrong": len(wrong_answers),
        "decision": decision,
        "cost": sum(run_cost(run_dir) for run_dir in run_dirs if run_dir.is_dir()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("items_root", type=Path)
    parser.add_argument("run_ids", nargs="+")
    args = parser.parse_args()

    results = [score_item(gold_file.parent, args.run_ids)
               for gold_file in sorted(args.items_root.glob("**/gold.json"))]
    for result in results:
        print(f"{result['decision']:<6} wrong={result['wrong']}  gold={result['gold']:<9} "
              f"answers={','.join(answer or '-' for answer in result['answers']):<20} {result['item']}")

    print()
    for source in sorted({result["item"].split("/")[0] for result in results}):
        source_results = [result for result in results if result["item"].startswith(source + "/")]
        total_runs = len(source_results) * len(args.run_ids)
        correct_runs = sum(result["correct"] for result in source_results)
        decisions = {decision: sum(result["decision"] == decision for result in source_results)
                     for decision in ("keep", "drop", "rerun")}
        print(f"{source}: correct {correct_runs}/{total_runs} runs; {decisions}")
    print(f"total cost ${sum(result['cost'] for result in results):.2f}")

    selection_file = args.items_root / "pilot-selection.json"
    selection_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"selection: {selection_file}")


if __name__ == "__main__":
    main()
