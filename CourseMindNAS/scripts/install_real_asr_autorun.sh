#!/usr/bin/env bash
set -euo pipefail

PROJECT="${COURSEMIND_PROJECT:-$HOME/coursemind-nas}"
LEGACY_VIDEO_ROOT="${COURSEMIND_LEGACY_VIDEO_ROOT:-$HOME/电脑备份文件/工作项目文件/NAS/NAS视频字幕/视频}"
SYNC_VIDEO_ROOT="${COURSEMIND_SYNC_VIDEO_ROOT:-$HOME/电脑备份文件/工作项目文件/NAS视频字幕}"
COMPOSE_FILE="${COURSEMIND_COMPOSE_FILE:-docker-compose.ugreen-local.yml}"
INTERVAL_SECONDS="${COURSEMIND_ASR_DAEMON_INTERVAL_SECONDS:-300}"
LIMIT="${COURSEMIND_ASR_DAEMON_LIMIT:-1}"
INSTALL_CRON=1
RECREATE_DOCKER=1

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/install_real_asr_autorun.sh [options]

Options:
  --sync-root PATH       One-way synced video root. Default: ~/电脑备份文件/工作项目文件/NAS视频字幕
  --legacy-root PATH     Existing old video folder. Default: ~/电脑备份文件/工作项目文件/NAS/NAS视频字幕/视频
  --interval-seconds N   Daemon interval. Default: 300
  --limit N              Videos processed per daemon round. Default: 1
  --no-cron              Do not install crontab keepalive.
  --no-docker-recreate   Do not recreate Docker containers after .env changes.
  --help                 Show this help.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --sync-root)
      SYNC_VIDEO_ROOT="${2:?missing value for --sync-root}"
      shift 2
      ;;
    --legacy-root)
      LEGACY_VIDEO_ROOT="${2:?missing value for --legacy-root}"
      shift 2
      ;;
    --interval-seconds)
      INTERVAL_SECONDS="${2:?missing value for --interval-seconds}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:?missing value for --limit}"
      shift 2
      ;;
    --no-cron)
      INSTALL_CRON=0
      shift
      ;;
    --no-docker-recreate)
      RECREATE_DOCKER=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$PROJECT"
mkdir -p CourseMind/logs

RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$PROJECT/CourseMind/logs/install_real_asr_autorun_$RUN_ID.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "== install CourseMind real ASR autorun =="
echo "time=$(date '+%Y-%m-%d %H:%M:%S')"
echo "project=$PROJECT"
echo "legacy_video_root=$LEGACY_VIDEO_ROOT"
echo "sync_video_root=$SYNC_VIDEO_ROOT"
echo "interval_seconds=$INTERVAL_SECONDS limit=$LIMIT"
echo "log_file=$LOG_FILE"

if [ ! -f .env ]; then
  echo "[ERROR] .env not found in $PROJECT" >&2
  exit 1
fi
if [ ! -d "$LEGACY_VIDEO_ROOT" ]; then
  echo "[WARN] legacy video root not found: $LEGACY_VIDEO_ROOT"
fi
if [ ! -d "$SYNC_VIDEO_ROOT" ]; then
  echo "[ERROR] sync video root not found: $SYNC_VIDEO_ROOT" >&2
  exit 1
fi
if ! grep -Eq '^(DASHSCOPE_API_KEY|TRANSCRIPTION_API_KEY)=.+' .env; then
  echo "[ERROR] missing DASHSCOPE_API_KEY or TRANSCRIPTION_API_KEY in .env" >&2
  exit 1
fi

backup=".env.bak.before_real_asr_autorun_$RUN_ID"
cp .env "$backup"
echo "env_backup=$PROJECT/$backup"

set_env_kv() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

set_env_kv HOST_VIDEO_ROOT "$LEGACY_VIDEO_ROOT"
set_env_kv HOST_UPLOAD_VIDEO_ROOT "$SYNC_VIDEO_ROOT"
set_env_kv AUTO_SCAN true
set_env_kv SCAN_RECURSIVE true
set_env_kv AUTO_PROCESS_NEW_VIDEO false
set_env_kv AUTO_PROCESS_NEW_VIDEOS false
set_env_kv AUTO_PROCESS_MAX_PER_ROUND 1
set_env_kv ASR_PROVIDER aliyun_dashscope
set_env_kv TRANSCRIPTION_PROVIDER aliyun_dashscope
set_env_kv ASR_MODEL fun-asr-realtime
set_env_kv TRANSCRIPTION_MODEL fun-asr-realtime
set_env_kv AUDIO_CHUNK_SECONDS 60
set_env_kv MAX_SINGLE_VIDEO_MINUTES 180
set_env_kv VIDEO_EXCLUDE_DIRS ".git,__pycache__,node_modules,coursemind-nas,CourseMind,processed,storage,CourseMind/processed,CourseMind/logs,CourseMind/backups,#SyncVersion,NAS回传归档,回传附件"

chmod +x scripts/run_real_asr_queue_once.sh scripts/run_real_asr_queue_daemon.sh scripts/ensure_real_asr_queue_daemon.sh

if [ "$RECREATE_DOCKER" = "1" ]; then
  echo "== recreate docker containers =="
  sudo docker compose -f "$COMPOSE_FILE" up -d --force-recreate backend frontend
  echo "== wait backend health =="
  for _ in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8766/healthz >/dev/null 2>&1; then
      echo "backend ready"
      break
    fi
    sleep 2
  done
fi

echo "== keep backend auto-process disabled =="
curl -fsS -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false,"auto_scan":true,"scan_recursive":true,"auto_process_max_per_round":1}' || true
printf '\n'

echo "== start queue daemon =="
bash scripts/ensure_real_asr_queue_daemon.sh --daemon-limit "$LIMIT" --interval-seconds "$INTERVAL_SECONDS"

if [ "$INSTALL_CRON" = "1" ]; then
  echo "== install user crontab keepalive =="
  cron_line="*/5 * * * * cd $PROJECT && bash scripts/ensure_real_asr_queue_daemon.sh --daemon-limit $LIMIT --interval-seconds $INTERVAL_SECONDS >> CourseMind/logs/real_asr_autorun.cron.log 2>&1"
  tmp_cron="$(mktemp)"
  crontab -l 2>/dev/null | grep -v 'ensure_real_asr_queue_daemon.sh' > "$tmp_cron" || true
  printf '%s\n' "$cron_line" >> "$tmp_cron"
  if crontab "$tmp_cron"; then
    echo "cron_installed=$cron_line"
  else
    echo "[WARN] user crontab failed; installing /etc/cron.d fallback with sudo"
    cron_file="/tmp/coursemind-real-asr.cron"
    cron_user="$(id -un)"
    {
      printf '%s\n' 'SHELL=/bin/bash'
      printf '%s\n' 'PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin'
      printf '*/5 * * * * %s cd %s && bash scripts/ensure_real_asr_queue_daemon.sh --daemon-limit %s --interval-seconds %s >> CourseMind/logs/real_asr_autorun.cron.log 2>&1\n' \
        "$cron_user" "$PROJECT" "$LIMIT" "$INTERVAL_SECONDS"
    } > "$cron_file"
    sudo cp "$cron_file" /etc/cron.d/coursemind-real-asr
    sudo chmod 0644 /etc/cron.d/coursemind-real-asr
    rm -f "$cron_file"
    echo "cron_installed=/etc/cron.d/coursemind-real-asr"
  fi
  rm -f "$tmp_cron"
else
  echo "cron_skipped"
fi

echo "== dry-run check =="
bash scripts/run_real_asr_queue_once.sh --dry-run --no-scan --limit 5

echo "[OK] CourseMind real ASR autorun installed."
