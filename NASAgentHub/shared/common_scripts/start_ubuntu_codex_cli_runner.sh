#!/usr/bin/env sh
set -eu

ROOT="${AGENTHUB_DIR:-/home/mana/NASAgentHub}"
RUNNER="${ROOT}/shared/common_scripts/ubuntu_codex_cli_runner.py"
LOG_DIR="${ROOT}/logs"
PID_FILE="${LOG_DIR}/ubuntu_codex_cli_runner.pid"
LOG_FILE="${LOG_DIR}/ubuntu_codex_cli_runner.nohup.log"

mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "UBUNTU_CODEX_CLI_RUNNER_ALREADY_RUNNING pid=$OLD_PID log=$LOG_FILE"
    exit 0
  fi
fi

nohup python3 "$RUNNER" >>"$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"
echo "UBUNTU_CODEX_CLI_RUNNER_STARTED pid=$PID log=$LOG_FILE"

