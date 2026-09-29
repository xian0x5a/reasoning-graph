"""Count what the agents of a resume-loop arm did with their memory file (issue #37).

    uv run tests/scenarios/exact-answer/loop_usage.py <items-root> <run-id> <arm>...

Reads the transcripts under <items-root>/<item>/<arm>/<run-id>/rounds/ of every finished loop.

Per arm:
- tool calls: all of them, the main driver of cost
- memory read on resume: rounds after the first whose agent opened a kept file
- graph arm only: `record` calls, writes refused because the state had stopped, hand edits of
  state.json, and renders that show computed belief (`html`, `mermaid`)
"""

import argparse
import json
import re
from pathlib import Path

from run_loop import ARM_KEPT_FILES, transcript_events

STATE_FILE = "state.json"
HAND_EDIT_TOOLS = re.compile(r"\b(python3?|sed|jq|perl|cp|mv)\b")
RENDER_COMMAND = re.compile(r"reasoning-graph\s+(html|mermaid)\b")
RECORD_COMMAND = re.compile(r"reasoning-graph\s+record\b")
STOPPED_STATE_ERROR = "already has a stop event"


def tool_calls(transcript: Path) -> list[dict]:
    return [block for event in transcript_events(transcript) if event.get("type") == "assistant"
            for block in event["message"]["content"] if block.get("type") == "tool_use"]


def tool_results(transcript: Path) -> list[str]:
    results = []
    for event in transcript_events(transcript):
        content = event["message"]["content"] if event.get("type") == "user" else None
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_result":
                body = block.get("content")
                results.append(body if isinstance(body, str) else json.dumps(body))
    return results


def call_text(call: dict) -> str:
    """The command of a shell call, or the path of a file tool call."""
    return str(call["input"].get("command") or call["input"].get("file_path") or "")


def edits_state_by_hand(call: dict) -> bool:
    text = call_text(call)
    if call["name"] in ("Edit", "Write"):
        return text.endswith(STATE_FILE)
    # Each shell line is judged alone, so a record and a hand edit in one call are told apart.
    return any(STATE_FILE in line and HAND_EDIT_TOOLS.search(line) and "reasoning-graph" not in line
               for line in re.split(r"\n|&&|;", text))


def arm_usage(arm: str, run_dirs: list[Path]) -> dict:
    usage = {"loops": len(run_dirs), "rounds": 0, "tool calls": 0, "resumed rounds": 0,
             "memory read on resume": 0}
    graph_usage = {"record calls": 0, "writes refused after a stop": 0,
                   "hand edits of the state": 0, "belief renders": 0}
    for run_dir in run_dirs:
        for round_dir in sorted((run_dir / "rounds").iterdir(), key=lambda path: int(path.name)):
            transcripts = sorted(round_dir.glob("*transcript.jsonl"))
            calls = [call for transcript in transcripts for call in tool_calls(transcript)]
            results = [result for transcript in transcripts for result in tool_results(transcript)]
            usage["rounds"] += 1
            usage["tool calls"] += len(calls)
            if round_dir.name != "1":
                usage["resumed rounds"] += 1
                solving_calls = tool_calls(round_dir / "transcript.jsonl")
                usage["memory read on resume"] += any(
                    kept_file in call_text(call) for call in solving_calls for kept_file in ARM_KEPT_FILES[arm])
            graph_usage["record calls"] += sum(bool(RECORD_COMMAND.search(call_text(call))) for call in calls)
            graph_usage["writes refused after a stop"] += sum(STOPPED_STATE_ERROR in result for result in results)
            graph_usage["hand edits of the state"] += sum(edits_state_by_hand(call) for call in calls)
            graph_usage["belief renders"] += sum(bool(RENDER_COMMAND.search(call_text(call))) for call in calls)
    return usage | (graph_usage if STATE_FILE in ARM_KEPT_FILES[arm] else {})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("items_root", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("arms", nargs="+", choices=sorted(ARM_KEPT_FILES))
    args = parser.parse_args()

    for arm in args.arms:
        run_dirs = sorted(loop_file.parent for loop_file in args.items_root.glob(f"*/{arm}/{args.run_id}/loop.json"))
        print(arm)
        for measure, value in arm_usage(arm, run_dirs).items():
            print(f"  {measure:<30} {value}")


if __name__ == "__main__":
    main()
