#!/usr/bin/env bash
# A/B benchmark runs: one arm on one scenario per run.
#
#   bench.sh prepare <scenario> <arm> <run-id>   # prints the workspace path
#   bench.sh collect <scenario> <arm> <run-id>   # copies outputs to test-results/
#
# The agent works in a scratch workspace outside the repo that holds only the
# problem file, so it cannot wander into validator.md or the skill's source.
# Start the agent with that workspace as cwd, `--session-dir <workspace>/session`,
# and the text of <workspace>/prompt.md as its first message.
set -euo pipefail

repo_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
scenarios_dir="$repo_root/tests/scenarios"
workspace_root="${RG_BENCH_WORKSPACE_ROOT:-/tmp/rg-bench}"

usage() { sed -n '2,5p' "$0" >&2; exit 2; }

[[ $# -eq 4 ]] || usage
command=$1 scenario=$2 arm=$3 run_id=$4
template="$scenarios_dir/_templates/$arm.md"
workspace="$workspace_root/$scenario/$arm/$run_id"
results="$repo_root/test-results/$scenario/$arm/$run_id"

prepare() {
  [[ -f $template ]] || { echo "unknown arm: $arm" >&2; exit 2; }
  [[ ! -e $workspace ]] || { echo "workspace exists: $workspace" >&2; exit 1; }
  mkdir -p "$workspace/session"
  cp "$scenarios_dir/$scenario/problem.md" "$workspace/problem.md"
  if [[ -d $scenarios_dir/$scenario/assets ]]; then
    cp -r "$scenarios_dir/$scenario/assets" "$workspace/assets"
  fi
  sed 's/{{PROBLEM_FILE}}/problem.md/g' "$template" > "$workspace/prompt.md"
  cat > "$workspace/meta.json" <<EOF
{"scenario": "$scenario", "arm": "$arm", "run_id": "$run_id",
 "skill_commit": "$(git -C "$repo_root" rev-parse --short HEAD)",
 "prepared_at": "$(date -Iseconds)"}
EOF
  echo "$workspace"
}

collect() {
  [[ -d $workspace ]] || { echo "no workspace: $workspace" >&2; exit 1; }
  mkdir -p "$results"
  # Agent-generated scripts and graph state come along; the problem copy does not.
  rsync -a --exclude problem.md --exclude assets "$workspace/" "$results/"
  echo "$results"
}

case $command in
  prepare) prepare ;;
  collect) collect ;;
  *) usage ;;
esac
