#!/usr/bin/env bash
# Run one arm headless on exact-answer items, several at once (issue #34).
#
#   run.sh <harness> <model> <arm> <run-id> <item-dir>...
#
#   harness   pi      model as pi's "provider/id", e.g. antigravity/gemini-3.8-flash
#             claude  model as a Claude Code model id, e.g. claude-sonnet-5
#   item-dir  from build_items.py, e.g. test-results/exact-answer/true-detective/*
#
# Each item goes through bench.sh prepare -> agent -> bench.sh collect, so runs land in
# <item-dir>/<arm>/<run-id>/. Items whose result dir already exists are skipped, so a
# rerun only fills gaps. Keep one harness and model per run-id prefix.
set -euo pipefail

THINKING_LEVEL=high
PARALLEL_RUNS="${RG_BENCH_PARALLEL:-6}"
RUN_TIMEOUT=30m

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
bench="$repo_root/tests/scenarios/bench.sh"
# bench.sh resolves <scenario> under this dir, and collects into test-results/<scenario>/.
export RG_BENCH_PROBLEMS_DIR="$repo_root/test-results"

run_pi() {
  local model=$1
  timeout "$RUN_TIMEOUT" pi -p --model "$model" --thinking "$THINKING_LEVEL" --session-dir session "$(cat prompt.md)" \
    > stdout.txt 2> stderr.txt
}

run_claude() {
  local model=$1
  # stream-json keeps the whole transcript, subagents included, inside the workspace;
  # the final "result" event carries the run's cost.
  timeout "$RUN_TIMEOUT" claude -p "$(cat prompt.md)" --model "$model" --effort "$THINKING_LEVEL" \
    --dangerously-skip-permissions --no-session-persistence \
    --output-format stream-json --verbose > transcript.jsonl 2> stderr.txt
}

run_item() {
  local harness=$1 model=$2 arm=$3 run_id=$4 item_dir scenario workspace
  item_dir=$(realpath "$5")
  scenario=${item_dir#"$RG_BENCH_PROBLEMS_DIR/"}
  if [[ -e $item_dir/$arm/$run_id ]]; then
    echo "skip  $scenario ($arm/$run_id exists)"
    return
  fi
  workspace=$("$bench" prepare "$scenario" "$arm" "$run_id")
  printf '{"harness": "%s", "model": "%s", "thinking": "%s"}\n' "$harness" "$model" "$THINKING_LEVEL" \
    > "$workspace/agent.json"
  # A failed or timed-out run is still collected; score_pilot.py reports it as having no answer.
  (cd "$workspace" && "run_$harness" "$model") \
    || echo "exit=$?" > "$workspace/failed.txt"
  "$bench" collect "$scenario" "$arm" "$run_id" > /dev/null
  echo "done  $scenario"
}

if [[ ${1:-} == --one ]]; then
  shift
  run_item "$@"
  exit
fi

[[ $# -ge 5 ]] || { sed -n '2,12p' "$0" >&2; exit 2; }
harness=$1 model=$2 arm=$3 run_id=$4
shift 4
[[ $harness == pi || $harness == claude ]] || { echo "unknown harness: $harness" >&2; exit 2; }
printf '%s\0' "$@" | xargs -0 -P "$PARALLEL_RUNS" -I{} "$0" --one "$harness" "$model" "$arm" "$run_id" {}
