#!/usr/bin/env bash
set -euo pipefail

PROJECT="${COURSEMIND_PROJECT:-$HOME/coursemind-nas}"
cd "$PROJECT"

echo "== stop CourseMind real ASR autorun =="

PID_FILE="$PROJECT/CourseMind/logs/real_asr_queue_daemon.pid"
if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "daemon_stopped pid=$pid"
  else
    echo "daemon_not_running"
  fi
  rm -f "$PID_FILE"
else
  echo "pid_file_not_found"
fi

if command -v crontab >/dev/null 2>&1; then
  tmp_cron="$(mktemp)"
  crontab -l 2>/dev/null | grep -v 'ensure_real_asr_queue_daemon.sh' > "$tmp_cron" || true
  crontab "$tmp_cron" || true
  rm -f "$tmp_cron"
  echo "user_cron_removed"
else
  echo "crontab_not_found"
fi

if [ -f /etc/cron.d/coursemind-real-asr ]; then
  sudo rm -f /etc/cron.d/coursemind-real-asr
  echo "system_cron_removed"
else
  echo "system_cron_not_found"
fi

echo "[OK] autorun stopped. .env is not modified by uninstall."
