#!/usr/bin/env bash
# A/B benchmark runs: one arm on one scenario per run.
#
#   bench.sh prepare <scenario> <arm> <run-id> [problem-file]   # prints the workspace path
#   bench.sh collect <scenario> <arm> <run-id>                  # copies outputs to test-results/
#
# problem-file defaults to problem.md; a variant such as problem.v4.md is copied in as problem.md.
#
# The agent works in a scratch workspace outside the repo that holds only the
# problem file, so it cannot wander into validator.md or the skill's source.
# Start the agent with that workspace as cwd, `--session-dir <workspace>/session`,
# and the text of <workspace>/prompt.md as its first message.
#
# RG_BENCH_PROBLEMS_DIR points <scenario> at problem packets outside tests/scenarios,
# for datasets that must stay out of git (see exact-answer/build_items.py).
set -euo pipefail

repo_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
scenarios_dir="$repo_root/tests/scenarios"
problems_dir="${RG_BENCH_PROBLEMS_DIR:-$scenarios_dir}"
workspace_root="${RG_BENCH_WORKSPACE_ROOT:-/tmp/rg-bench}"

usage() { sed -n '2,7p' "$0" >&2; exit 2; }

[[ $# -eq 4 || $# -eq 5 ]] || usage
command=$1 scenario=$2 arm=$3 run_id=$4 problem_file=${5:-problem.md}
template="$scenarios_dir/_templates/$arm.md"
workspace="$workspace_root/$scenario/$arm/$run_id"
results="$repo_root/test-results/$scenario/$arm/$run_id"

prepare() {
  [[ -f $template ]] || { echo "unknown arm: $arm" >&2; exit 2; }
  [[ ! -e $workspace ]] || { echo "workspace exists: $workspace" >&2; exit 1; }
  mkdir -p "$workspace/session"
  cp "$problems_dir/$scenario/$problem_file" "$workspace/problem.md"
  if [[ -d $problems_dir/$scenario/assets ]]; then
    cp -r "$problems_dir/$scenario/assets" "$workspace/assets"
  fi
  sed 's/{{PROBLEM_FILE}}/problem.md/g' "$template" > "$workspace/prompt.md"
  cat > "$workspace/meta.json" <<EOF
{"scenario": "$scenario", "problem_file": "$problem_file", "arm": "$arm", "run_id": "$run_id",
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
