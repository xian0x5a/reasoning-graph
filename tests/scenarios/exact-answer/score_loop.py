"""Compare the arms of the resume loop (issue #37).

    uv run tests/scenarios/exact-answer/score_loop.py <items-root> <run-id> <arm>...

Reads <items-root>/<item>/<arm>/<run-id>/loop.json from run_loop.py, for every item that has
one for each arm given, so the arms are compared on the same items.

Per arm:
- first submit right: the answer letter of round 1, by exact match. Round 1 has no memory to
  use, so this is the accuracy guard, not a memory measure.
- passed: the loop ended with the right letter and every key point covered
- submits: rounds used, where a run that never passed counts its full cap
- repeated answers: submits whose wrong letter an earlier round had already been told is wrong
- hint used: of the hints given, how often the next submit covered the hinted key point
- cost: the agent's sessions, without the scorer

With both the no-memory and the graph arm given, it also prints the accuracy guard: the skill
hurts when more items are right only without it than only with it, at McNemar p < 0.10. This
is the score_ab.py rule read in reverse, on the first submit.
"""

import argparse
import json
from pathlib import Path

from score_ab import VALUE_P_THRESHOLD, mcnemar_exact_p

COVERED = "covered"
# The no-memory arm's first submit is an answer without the skill.
GUARD_BASELINE_ARM = "no-memory"
GUARD_SKILL_ARM = "graph"


def hint_outcomes(rounds: list[dict]) -> list[bool]:
    """For each hint given, whether the next submit covered the key point it was about."""
    return [later["verdicts"][earlier["first_failed"]] == COVERED
            for earlier, later in zip(rounds, rounds[1:]) if earlier.get("hint")]


def arm_summary(loops: list[dict]) -> dict:
    hints = [outcome for loop in loops for outcome in hint_outcomes(loop["rounds"])]
    return {
        "items": len(loops),
        "first submit right": sum(loop["first_submit_correct"] for loop in loops),
        "passed": sum(loop["passed"] for loop in loops),
        "submits": sum(loop["submits"] for loop in loops),
        "repeated answers": sum(loop["repeated_rejected_answers"] for loop in loops),
        "hints given": len(hints),
        "hint used": sum(hints),
        "cost": round(sum(loop["cost"] for loop in loops), 2),
    }


def accuracy_guard(baseline_loops: list[dict], skill_loops: list[dict]) -> str:
    pairs = [(baseline["first_submit_correct"], skill["first_submit_correct"])
             for baseline, skill in zip(baseline_loops, skill_loops)]
    baseline_only_right = sum(baseline and not skill for baseline, skill in pairs)
    skill_only_right = sum(skill and not baseline for baseline, skill in pairs)
    p_value = mcnemar_exact_p(skill_only_right, baseline_only_right)
    hurts = baseline_only_right > skill_only_right and p_value < VALUE_P_THRESHOLD
    return (f"accuracy guard: right only without the skill {baseline_only_right}, "
            f"right only with it {skill_only_right}, McNemar exact p = {p_value:.3f}: "
            f"{'the skill hurts' if hurts else 'no harm shown'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("items_root", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("arms", nargs="+")
    args = parser.parse_args()

    loops_by_item = {}
    for item_dir in sorted(path.parent for path in args.items_root.glob("*/rubric.json")):
        loop_files = [item_dir / arm / args.run_id / "loop.json" for arm in args.arms]
        if all(loop_file.is_file() for loop_file in loop_files):
            loops_by_item[item_dir.name] = [json.loads(loop_file.read_text(encoding="utf-8"))
                                            for loop_file in loop_files]

    for item, loops in loops_by_item.items():
        per_arm = "  ".join(f"{arm}: {'pass' if loop['passed'] else 'fail'} in {loop['submits']}/{loop['max_rounds']}"
                            for arm, loop in zip(args.arms, loops))
        print(f"{item:<36} {per_arm}")

    print()
    summaries = {arm: arm_summary([loops[index] for loops in loops_by_item.values()])
                 for index, arm in enumerate(args.arms)}
    for measure in next(iter(summaries.values())):
        values = "  ".join(f"{arm}: {summary[measure]}" for arm, summary in summaries.items())
        print(f"{measure:<20} {values}")

    if {GUARD_BASELINE_ARM, GUARD_SKILL_ARM} <= set(args.arms):
        loops_of = {arm: [loops[index] for loops in loops_by_item.values()] for index, arm in enumerate(args.arms)}
        print()
        print(accuracy_guard(loops_of[GUARD_BASELINE_ARM], loops_of[GUARD_SKILL_ARM]))


if __name__ == "__main__":
    main()
