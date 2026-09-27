#!/usr/bin/env bash
# Run one arm headless on exact-answer items, several at once (issue #34).
#
#   run.sh <arm> <run-id> <item-dir>...     # item dirs from build_items.py, e.g. test-results/exact-answer/*/*
#
# Each item goes through bench.sh prepare -> pi -p -> bench.sh collect, so runs land in
# <item-dir>/<arm>/<run-id>/. Items whose result dir already exists are skipped, so a
# rerun only fills gaps. The model settings match the #33 Gemini rerun.
set -euo pipefail

MODEL_PROVIDER=antigravity
MODEL_ID=gemini-3.8-flash
THINKING_LEVEL=high
PARALLEL_RUNS="${RG_BENCH_PARALLEL:-6}"
RUN_TIMEOUT=30m

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
bench="$repo_root/tests/scenarios/bench.sh"
# bench.sh resolves <scenario> under this dir, and collects into test-results/<scenario>/.
export RG_BENCH_PROBLEMS_DIR="$repo_root/test-results"

run_item() {
  local arm=$1 run_id=$2 item_dir scenario workspace
  item_dir=$(realpath "$3")
  scenario=${item_dir#"$RG_BENCH_PROBLEMS_DIR/"}
  if [[ -e $item_dir/$arm/$run_id ]]; then
    echo "skip  $scenario ($arm/$run_id exists)"
    return
  fi
  workspace=$("$bench" prepare "$scenario" "$arm" "$run_id")
  # A failed or timed-out run is still collected; score.py reports it as having no answer.
  (cd "$workspace" && timeout "$RUN_TIMEOUT" pi -p \
    --provider "$MODEL_PROVIDER" --model "$MODEL_ID" --thinking "$THINKING_LEVEL" \
    --session-dir "$workspace/session" "$(cat prompt.md)" \
    > "$workspace/stdout.txt" 2> "$workspace/stderr.txt") || echo "exit=$?" > "$workspace/failed.txt"
  "$bench" collect "$scenario" "$arm" "$run_id" > /dev/null
  echo "done  $scenario"
}

if [[ ${1:-} == --one ]]; then
  shift
  run_item "$@"
  exit
fi

[[ $# -ge 3 ]] || { sed -n '2,8p' "$0" >&2; exit 2; }
arm=$1 run_id=$2
shift 2
printf '%s\0' "$@" | xargs -0 -P "$PARALLEL_RUNS" -I{} "$0" --one "$arm" "$run_id" {}
