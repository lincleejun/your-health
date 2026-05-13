#!/usr/bin/env bash
# Ralph loop runner.
#
# Reads PROMPT.md and pipes it to `claude -p` in a loop. Each iteration does
# exactly one task from SPEC.md under the rules in AGENTS.md. The loop stops
# when the agent prints one of the terminal tokens on its final line.
#
# Usage:
#   ./ralph.sh                # loop until done / blocked / user gate
#   ./ralph.sh --max 5        # cap iterations
#   ./ralph.sh --dry          # show what would run, do nothing
#
# Requires `claude` (Claude Code CLI) on PATH.

set -euo pipefail

MAX_ITERATIONS=50
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max) MAX_ITERATIONS="$2"; shift 2 ;;
    --dry) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI not found on PATH" >&2
  exit 1
fi

for required in AGENTS.md SPEC.md PROMPT.md; do
  [[ -f "$required" ]] || { echo "error: missing $required" >&2; exit 1; }
done

mkdir -p .ralph
LOG_DIR=".ralph/logs"
mkdir -p "$LOG_DIR"

iteration=0
while (( iteration < MAX_ITERATIONS )); do
  iteration=$((iteration + 1))
  stamp=$(date +%Y%m%d-%H%M%S)
  log="$LOG_DIR/iter-$(printf '%03d' "$iteration")-$stamp.log"

  echo "──────────────────────────────────────────────────────────────"
  echo "  Ralph iteration $iteration / $MAX_ITERATIONS  →  $log"
  echo "──────────────────────────────────────────────────────────────"

  if (( DRY_RUN == 1 )); then
    echo "(dry run) would invoke: claude -p < PROMPT.md"
    break
  fi

  # Stream output to both terminal and log file.
  set +e
  claude -p --dangerously-skip-permissions < PROMPT.md 2>&1 | tee "$log"
  status=${PIPESTATUS[0]}
  set -e

  if (( status != 0 )); then
    echo "claude exited non-zero ($status). Stopping loop." >&2
    exit "$status"
  fi

  last_line=$(tail -n 1 "$log" | tr -d '[:space:]')
  case "$last_line" in
    *RALPH_DONE_ITERATION*)
      echo "  ✓ iteration done, continuing"
      ;;
    *RALPH_USER_GATE*)
      echo "  🛑 user test gate hit. Run the manual test, then re-launch ralph.sh."
      exit 0
      ;;
    *RALPH_BLOCKED*)
      echo "  ⚠ blocked. See SPEC.md ## Questions / ## Blockers."
      exit 0
      ;;
    *RALPH_ALL_DONE*)
      echo "  🎉 all tasks complete."
      exit 0
      ;;
    *)
      echo "  ⚠ no terminal token on last line. Stopping to avoid runaway." >&2
      echo "  last line: $last_line" >&2
      exit 1
      ;;
  esac
done

echo "Hit MAX_ITERATIONS ($MAX_ITERATIONS). Stopping."
