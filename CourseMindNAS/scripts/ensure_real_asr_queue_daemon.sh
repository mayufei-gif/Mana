#!/usr/bin/env bash
set -euo pipefail

PROJECT="${COURSEMIND_PROJECT:-$HOME/coursemind-nas}"
INTERVAL_SECONDS="${COURSEMIND_ASR_DAEMON_INTERVAL_SECONDS:-300}"
LIMIT="${COURSEMIND_ASR_DAEMON_LIMIT:-1}"
EXTRA_ARGS=()

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
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

cd "$PROJECT"
mkdir -p CourseMind/logs

PID_FILE="$PROJECT/CourseMind/logs/real_asr_queue_daemon.pid"
NOHUP_LOG="$PROJECT/CourseMind/logs/real_asr_queue_daemon.nohup.log"

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "ASR_DAEMON_ALREADY_RUNNING pid=$pid"
    exit 0
  fi
fi

nohup bash "$PROJECT/scripts/run_real_asr_queue_daemon.sh" \
  --daemon-limit "$LIMIT" \
  --interval-seconds "$INTERVAL_SECONDS" \
  "${EXTRA_ARGS[@]}" \
  > "$NOHUP_LOG" 2>&1 &

echo "ASR_DAEMON_STARTED pid=$! log=$NOHUP_LOG"
