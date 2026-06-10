#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/mana/InfoRadar"
PYTHON="/home/mana/inforadar-runtime/venv/bin/python"
HOST="127.0.0.1"
PORT="8769"
HEALTH_URL="http://${HOST}:${PORT}/api/health"
PROCESS_PATTERN="uvicorn web.backend.app:app --host ${HOST} --port ${PORT}"
LOG_DIR="/home/mana/.cache/inforadar-watchdog"
WATCHDOG_LOG="${LOG_DIR}/watchdog.log"
APP_LOG="/tmp/inforadar-web-restart.log"
LOCK_FILE="${LOG_DIR}/watchdog.lock"

mkdir -p "${LOG_DIR}"
exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" >> "${WATCHDOG_LOG}"
}

health_ok() {
  curl -fsS --max-time 8 "${HEALTH_URL}" >/dev/null
}

if health_ok; then
  exit 0
fi

sleep 3
if health_ok; then
  log "first health check failed, second check recovered"
  exit 0
fi

log "health check failed twice; restarting InfoRadar Web on ${HOST}:${PORT}"

pids="$(pgrep -f -- "${PROCESS_PATTERN}" || true)"
if [ -n "${pids}" ]; then
  log "stopping old pids: ${pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 2
  alive="$(pgrep -f -- "${PROCESS_PATTERN}" || true)"
  if [ -n "${alive}" ]; then
    log "force killing old pids: ${alive//$'\n'/ }"
    # shellcheck disable=SC2086
    kill -9 ${alive} 2>/dev/null || true
    sleep 1
  fi
else
  log "no existing uvicorn pid found"
fi

cd "${ROOT}"
nohup "${PYTHON}" -m uvicorn web.backend.app:app --host "${HOST}" --port "${PORT}" >> "${APP_LOG}" 2>&1 < /dev/null &
new_pid="$!"
log "started new uvicorn pid=${new_pid}"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  if health_ok; then
    log "service recovered pid=${new_pid}"
    exit 0
  fi
done

log "service did not recover after restart pid=${new_pid}"
exit 1
