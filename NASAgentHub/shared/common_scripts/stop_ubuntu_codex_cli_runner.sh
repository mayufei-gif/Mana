#!/usr/bin/env sh
set -eu

ROOT="${AGENTHUB_DIR:-/home/mana/NASAgentHub}"
PID_FILE="${ROOT}/logs/ubuntu_codex_cli_runner.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "UBUNTU_CODEX_CLI_RUNNER_NOT_RUNNING"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "UBUNTU_CODEX_CLI_RUNNER_STOPPED pid=$PID"
else
  echo "UBUNTU_CODEX_CLI_RUNNER_STALE pid=$PID"
fi
rm -f "$PID_FILE"

