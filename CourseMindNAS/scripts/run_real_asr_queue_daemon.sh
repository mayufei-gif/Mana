#!/usr/bin/env bash
set -euo pipefail

PROJECT="${COURSEMIND_PROJECT:-$HOME/coursemind-nas}"
INTERVAL_SECONDS="${COURSEMIND_ASR_DAEMON_INTERVAL_SECONDS:-300}"
LIMIT="${COURSEMIND_ASR_DAEMON_LIMIT:-1}"
ONCE_SCRIPT="$PROJECT/scripts/run_real_asr_queue_once.sh"
LOG_DIR="$PROJECT/CourseMind/logs"
PID_FILE="$LOG_DIR/real_asr_queue_daemon.pid"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run_real_asr_queue_daemon.sh [options passed to run_real_asr_queue_once.sh]

Daemon options:
  --interval-seconds N  Sleep seconds between rounds. Default: 300
  --daemon-limit N      Default --limit for each round. Default: 1
  --help                Show this help.

Common examples:
  nohup bash scripts/run_real_asr_queue_daemon.sh --daemon-limit 1 > CourseMind/logs/real_asr_queue_daemon.nohup.log 2>&1 &
  bash scripts/run_real_asr_queue_daemon.sh --interval-seconds 600 --folder "初级会计"
USAGE
}

PASSTHROUGH=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --interval-seconds)
      INTERVAL_SECONDS="${2:?missing value for --interval-seconds}"
      shift 2
      ;;
    --daemon-limit)
      LIMIT="${2:?missing value for --daemon-limit}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      PASSTHROUGH+=("$1")
      shift
      ;;
  esac
done

if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [ "$INTERVAL_SECONDS" -lt 30 ]; then
  echo "[ERROR] --interval-seconds must be an integer >= 30." >&2
  exit 2
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [ "$LIMIT" -lt 1 ]; then
  echo "[ERROR] --daemon-limit must be a positive integer." >&2
  exit 2
fi

cd "$PROJECT"
mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[ERROR] real ASR queue daemon already running: pid=$old_pid"
    exit 1
  fi
fi

echo "$$" > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT INT TERM

echo "== CourseMind real ASR queue daemon =="
echo "pid=$$"
echo "project=$PROJECT"
echo "interval_seconds=$INTERVAL_SECONDS limit=$LIMIT"
echo "pid_file=$PID_FILE"

while true; do
  echo "== daemon round $(date '+%Y-%m-%d %H:%M:%S') =="
  if ! bash "$ONCE_SCRIPT" --limit "$LIMIT" "${PASSTHROUGH[@]}"; then
    echo "[WARN] queue once failed at $(date '+%Y-%m-%d %H:%M:%S'); next round will retry."
  fi
  sleep "$INTERVAL_SECONDS"
done
