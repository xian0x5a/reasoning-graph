"""Score the skill vs no-skill A/B on the items the pilot kept.

    uv run tests/scenarios/exact-answer/score_ab.py <items-root> <run-id>

Reads <items-root>/pilot-selection.json from score_pilot.py and uses every item it kept.
Each kept item needs one <run-id> run per arm, made with the claude harness: the network
check reads its stream-json transcript. An item where either arm touched the network is
excluded from every metric, since the True Detective solutions are public.

Metrics, by exact match against gold: accuracy per arm, and McNemar's exact test on the
pairs where the arms disagree. Cost per arm is reported.

Verdict rule, agreed before any A/B run (the sample is small, hence p < 0.10):
- adds value: skill-only-right > no-skill-only-right and McNemar p < 0.10
- no gain: skill-only-right <= no-skill-only-right
- inconclusive: anything else; report it as such and claim no gain
"""

import argparse
import json
import math
import re
from pathlib import Path

from score_pilot import final_answer, run_cost

SKILL_ARM = "reasoning-graph"
NO_SKILL_ARM = "no-skill"
NETWORK_TOOLS = {"WebSearch", "WebFetch"}
NETWORK_COMMAND_PATTERN = re.compile(r"\b(curl|wget|https?://)")
VALUE_P_THRESHOLD = 0.10


def transcript_events(run_dir: Path) -> list[dict]:
    transcript = run_dir / "transcript.jsonl"
    return [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line]


def network_calls(run_dir: Path) -> list[str]:
    """Tool calls that reach the network, subagents included, as short descriptions."""
    calls = []
    for event in transcript_events(run_dir):
        if event.get("type") != "assistant":
            continue
        for block in event["message"]["content"]:
            if block.get("type") != "tool_use":
                continue
            tool_input = json.dumps(block.get("input"))
            if (block["name"] in NETWORK_TOOLS or block["name"].startswith("mcp__")
                    or NETWORK_COMMAND_PATTERN.search(tool_input)):
                calls.append(f"{block['name']} {tool_input[:80]}")
    return calls


def mcnemar_exact_p(skill_only_right: int, no_skill_only_right: int) -> float:
    """Two-sided exact binomial test of the disagreeing pairs against a 50/50 split."""
    disagreements = skill_only_right + no_skill_only_right
    if disagreements == 0:
        return 1.0
    tail = min(skill_only_right, no_skill_only_right)
    one_tail = sum(math.comb(disagreements, k) for k in range(tail + 1)) / 2 ** disagreements
    return min(1.0, 2 * one_tail)


def verdict(skill_only_right: int, no_skill_only_right: int) -> str:
    if skill_only_right <= no_skill_only_right:
        return "no gain"
    if mcnemar_exact_p(skill_only_right, no_skill_only_right) < VALUE_P_THRESHOLD:
        return "adds value"
    return "inconclusive"


def score_item(item_dir: Path, run_id: str) -> dict:
    gold = json.loads((item_dir / "gold.json").read_text(encoding="utf-8"))
    runs = {arm: item_dir / arm / run_id for arm in (NO_SKILL_ARM, SKILL_ARM)}
    missing = [arm for arm, run_dir in runs.items() if not run_dir.is_dir()]
    if missing:
        raise SystemExit(f"{item_dir.name}: no {run_id} run for {', '.join(missing)}")
    answers = {arm: final_answer(run_dir, gold["choices"]) for arm, run_dir in runs.items()}
    return {
        "item": item_dir.name,
        "gold": gold["answer"],
        "answers": answers,
        "correct": {arm: answer == gold["answer"] for arm, answer in answers.items()},
        "network_calls": {arm: network_calls(run_dir) for arm, run_dir in runs.items()},
        "cost": {arm: run_cost(run_dir) for arm, run_dir in runs.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("items_root", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()

    selection = json.loads((args.items_root / "pilot-selection.json").read_text(encoding="utf-8"))
    kept_items = [args.items_root / result["item"].split("/")[-1]
                  for result in selection if result["decision"] == "keep"]
    results = [score_item(item_dir, args.run_id) for item_dir in kept_items]

    contaminated = [result for result in results if any(result["network_calls"].values())]
    scored = [result for result in results if result not in contaminated]
    for result in results:
        mark = "EXCLUDED network" if result in contaminated else ""
        print(f"gold={result['gold']}  no-skill={result['answers'][NO_SKILL_ARM] or '-'}  "
              f"skill={result['answers'][SKILL_ARM] or '-'}  {result['item']} {mark}")

    def count(predicate) -> int:
        return sum(1 for result in scored if predicate(result))

    skill_only_right = count(lambda r: r["correct"][SKILL_ARM] and not r["correct"][NO_SKILL_ARM])
    no_skill_only_right = count(lambda r: r["correct"][NO_SKILL_ARM] and not r["correct"][SKILL_ARM])

    print(f"\nitems: {len(scored)} scored, {len(contaminated)} excluded for network use")
    for arm in (NO_SKILL_ARM, SKILL_ARM):
        print(f"{arm}: accuracy {count(lambda r, arm=arm: r['correct'][arm])}/{len(scored)}, "
              f"cost ${sum(result['cost'][arm] for result in results):.2f}")
    print(f"disagreements: skill-only right {skill_only_right}, no-skill-only right {no_skill_only_right}, "
          f"McNemar exact p = {mcnemar_exact_p(skill_only_right, no_skill_only_right):.3f}")
    print(f"VERDICT: {verdict(skill_only_right, no_skill_only_right)}")

    report_file = args.items_root / f"ab-{args.run_id}.json"
    report_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"report: {report_file}")


if __name__ == "__main__":
    main()
