"""Run one arm of the resume loop on exact-answer items, several at once (issue #37).

    uv run tests/scenarios/exact-answer/run_loop.py <model> <arm> <run-id> <item-dir>...

    model     a Claude Code model id, e.g. claude-sonnet-5-5
    item-dir  an item with a rubric.json from draft_rubrics.py

A round is one fresh session: the agent writes answer.md and score_submit.py grades it.
A rejected submit is answered in that same session with "wrong" plus the rubric hint of the
first key point it failed, so the feedback exists only in the conversation. The agent then
writes handoff.md, which stands in for a compaction summary: headless Claude Code cannot be
made to compact. The next round is a new session that gets the handoff text, in a workspace
that keeps only the problem and the files the arm may keep.

An item gets one more round than its rubric has key points: after the last hint there is
nothing new to tell the agent. Results land in <item-dir>/<arm>/<run-id>/, with loop.json as
the summary; an item whose result dir exists is skipped.
"""

import argparse
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from score_submit import DEFAULT_MODEL as SCORER_MODEL
from score_submit import score_submit

THINKING_LEVEL = "high"
SESSION_TIMEOUT_SECONDS = 30 * 60
PARALLEL_RUNS = int(os.environ.get("RG_BENCH_PARALLEL", "6"))

# What survives a context reset besides the handoff text, per arm.
ARM_KEPT_FILES = {
    "compaction-only": [],
    "notes-file": ["notes.md"],
}
PROBLEM_FILES = ["problem.md", "assets"]

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCH = REPO_ROOT / "tests/scenarios/bench.sh"
PROBLEMS_DIR = REPO_ROOT / "test-results"

FEEDBACK_PROMPT = """Your submit was graded and is not accepted.

{letter_feedback}
{hint_line}
Your context is reset after this turn. Do not continue solving now. Write `handoff.md`: a summary of everything you need to continue this task in a fresh context.
"""

CONTINUE_PROMPT = """{arm_prompt}
You are continuing this task after a context reset. This summary was written before the reset:

<handoff>
{handoff}
</handoff>
"""


def run_session(workspace: Path, prompt: str, model: str, transcript: Path, resume: str | None = None) -> str:
    """Run one headless turn in the workspace, keep its transcript, and return the session id."""
    command = ["claude", "-p", prompt, "--model", model, "--effort", THINKING_LEVEL,
               "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
    if resume:
        command += ["--resume", resume]
    with transcript.open("w", encoding="utf-8") as output:
        subprocess.run(command, cwd=workspace, stdout=output, stderr=subprocess.PIPE, text=True,
                       timeout=SESSION_TIMEOUT_SECONDS, check=True)
    return next(event["session_id"] for event in transcript_events(transcript) if "session_id" in event)


def transcript_events(transcript: Path) -> list[dict]:
    return [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line]


def session_cost(transcript: Path) -> float:
    # A run with a background subagent emits its running total more than once, so take the last.
    totals = [event["total_cost_usd"] for event in transcript_events(transcript) if event.get("type") == "result"]
    return totals[-1]


def take_file(workspace: Path, name: str, round_dir: Path) -> str:
    """Move a file the agent wrote out of the workspace and return its text, or "" when missing."""
    source = workspace / name
    if not source.is_file():
        return ""
    shutil.move(source, round_dir / name)
    return (round_dir / name).read_text(encoding="utf-8")


def reset_workspace(workspace: Path, arm: str, round_dir: Path) -> None:
    """Keep the problem and the arm's files; everything else the agent left goes to the round's results."""
    leftovers = round_dir / "workspace"
    leftovers.mkdir()
    for kept_file in ARM_KEPT_FILES[arm]:
        if (workspace / kept_file).exists():
            shutil.copy(workspace / kept_file, round_dir / kept_file)
    for entry in workspace.iterdir():
        if entry.name not in PROBLEM_FILES + ARM_KEPT_FILES[arm]:
            shutil.move(entry, leftovers / entry.name)


def feedback_prompt(score: dict, rubric: dict) -> tuple[str, str | None]:
    if score["letter"] is None:
        letter_feedback = "No valid final answer line was found."
    elif score["letter_correct"]:
        letter_feedback = f"Answer {score['letter']} is correct, but the reasoning has a gap."
    else:
        letter_feedback = f"Answer {score['letter']} is wrong."
    hint = next((key_point["hint"] for key_point in rubric["key_points"]
                 if key_point["id"] == score["first_failed"]), None)
    hint_line = f"Hint: {hint}\n" if hint else ""
    return FEEDBACK_PROMPT.format(letter_feedback=letter_feedback, hint_line=hint_line), hint


def run_item(item_dir: Path, model: str, arm: str, run_id: str) -> str:
    item_dir = item_dir.resolve()
    scenario = str(item_dir.relative_to(PROBLEMS_DIR))
    results = item_dir / arm / run_id
    if results.exists():
        return f"skip  {scenario} ({arm}/{run_id} exists)"

    rubric = json.loads((item_dir / "rubric.json").read_text(encoding="utf-8"))
    max_rounds = len(rubric["key_points"]) + 1
    prepared = subprocess.run([BENCH, "prepare", scenario, arm, run_id], capture_output=True, text=True,
                              check=True, env={**os.environ, "RG_BENCH_PROBLEMS_DIR": str(PROBLEMS_DIR)})
    workspace = Path(prepared.stdout.strip())
    arm_prompt = (workspace / "prompt.md").read_text(encoding="utf-8")

    rounds = []
    prompt = arm_prompt
    for round_number in range(1, max_rounds + 1):
        round_dir = results / "rounds" / str(round_number)
        round_dir.mkdir(parents=True)
        session_id = run_session(workspace, prompt, model, round_dir / "transcript.jsonl")
        answer_text = take_file(workspace, "answer.md", round_dir)
        score = score_submit(item_dir, answer_text, SCORER_MODEL)
        round_record = {"round": round_number, **score, "cost": session_cost(round_dir / "transcript.jsonl")}
        rounds.append(round_record)
        if score["passed"] or round_number == max_rounds:
            reset_workspace(workspace, arm, round_dir)
            break

        feedback, hint = feedback_prompt(score, rubric)
        run_session(workspace, feedback, model, round_dir / "feedback-transcript.jsonl", resume=session_id)
        handoff = take_file(workspace, "handoff.md", round_dir)
        round_record |= {"hint": hint, "handoff_written": bool(handoff),
                         "cost": round_record["cost"] + session_cost(round_dir / "feedback-transcript.jsonl")}
        reset_workspace(workspace, arm, round_dir)
        prompt = CONTINUE_PROMPT.format(arm_prompt=arm_prompt, handoff=handoff)

    rejected_letters = [entry["letter"] for entry in rounds[:-1]]
    summary = {
        "item": scenario, "arm": arm, "run_id": run_id, "model": model, "thinking": THINKING_LEVEL,
        "scorer_model": SCORER_MODEL, "max_rounds": max_rounds,
        "passed": rounds[-1]["passed"], "submits": len(rounds),
        "first_submit_correct": rounds[0]["letter_correct"],
        "repeated_rejected_answers": sum(
            entry["letter"] in rejected_letters[:index] and not entry["letter_correct"]
            for index, entry in enumerate(rounds)),
        "cost": sum(entry["cost"] for entry in rounds),
        "rounds": rounds,
    }
    (results / "loop.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return f"done  {scenario} passed={summary['passed']} submits={summary['submits']}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model")
    parser.add_argument("arm", choices=sorted(ARM_KEPT_FILES))
    parser.add_argument("run_id")
    parser.add_argument("item_dirs", nargs="+", type=Path)
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=PARALLEL_RUNS) as pool:
        runs = [pool.submit(run_item, item_dir, args.model, args.arm, args.run_id) for item_dir in args.item_dirs]
        # result() re-raises a failed item's error after the other items have finished.
        for run in runs:
            print(run.result())


if __name__ == "__main__":
    main()
