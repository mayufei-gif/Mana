#!/usr/bin/env sh
set -eu

PROJECT="/home/yma648692gmail.com/coursemind-nas"
COMPOSE="docker compose -f docker-compose.ugreen-local.yml"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$PROJECT/CourseMind/logs"
STATUS_FILE="$LOG_DIR/full_real_asr_status_$RUN_ID.txt"
ENV_BACKUP="$PROJECT/.env.bak.before_full_real_asr_$RUN_ID"
VIDEOS="6 5"

mkdir -p "$LOG_DIR"
cd "$PROJECT"
cp .env "$ENV_BACKUP"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$STATUS_FILE"
}

set_env_kv() {
  key="$1"
  value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

wait_backend() {
  log "wait backend health"
  for i in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8766/healthz >/dev/null 2>&1; then
      log "backend ready"
      return 0
    fi
    sleep 2
  done
  log "backend health timeout"
  return 1
}

restore_env() {
  code=$?
  log "restore env, exit_code=$code"
  cp "$ENV_BACKUP" .env
  chown yma648692gmail.com:admin .env 2>/dev/null || true
  $COMPOSE down >> "$STATUS_FILE" 2>&1 || true
  $COMPOSE up -d >> "$STATUS_FILE" 2>&1 || true
  log "restore complete"
  exit "$code"
}
trap restore_env EXIT INT TERM

log "full real ASR run started: videos=$VIDEOS"
log "env backup: $ENV_BACKUP"

if ! grep -Eq '^(DASHSCOPE_API_KEY|TRANSCRIPTION_API_KEY)=.+' .env; then
  log "missing DASHSCOPE_API_KEY or TRANSCRIPTION_API_KEY"
  exit 1
fi

curl -fsS -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false}' >> "$STATUS_FILE" 2>&1 || true
printf '\n' >> "$STATUS_FILE"

set_env_kv AUTO_PROCESS_NEW_VIDEO false
set_env_kv AUTO_PROCESS_NEW_VIDEOS false
set_env_kv ASR_PROVIDER aliyun_dashscope
set_env_kv TRANSCRIPTION_PROVIDER aliyun_dashscope
set_env_kv ASR_MODEL fun-asr-realtime
set_env_kv TRANSCRIPTION_MODEL fun-asr-realtime
set_env_kv AUDIO_CHUNK_SECONDS 60
set_env_kv MAX_SINGLE_VIDEO_MINUTES 180

log "recreate containers with real ASR env"
$COMPOSE down >> "$STATUS_FILE" 2>&1
$COMPOSE up -d >> "$STATUS_FILE" 2>&1
wait_backend

curl -fsS -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false}' >> "$STATUS_FILE" 2>&1 || true
printf '\n' >> "$STATUS_FILE"

for VIDEO_ID in $VIDEOS; do
  log "start reprocess video=$VIDEO_ID"
  curl -fsS -X POST "http://127.0.0.1:8766/api/videos/${VIDEO_ID}/reprocess" >> "$STATUS_FILE"
  printf '\n' >> "$STATUS_FILE"
  python3 - "$VIDEO_ID" >> "$STATUS_FILE" 2>&1 <<'PY'
import json
import sys
import time
import urllib.request

video_id = int(sys.argv[1])
status_url = f"http://127.0.0.1:8766/api/videos/{video_id}/status"
deadline = time.time() + (6 * 60 * 60)
last_line = None
while time.time() < deadline:
    with urllib.request.urlopen(status_url, timeout=20) as resp:
        payload = json.load(resp)
    video = payload["data"]["video"]
    job = payload["data"].get("job") or {}
    line = (
        time.strftime("%Y-%m-%d %H:%M:%S")
        + f" video={video_id} status={video.get('status')} subtitle={video.get('subtitle_status')} "
        + f"analysis={video.get('analysis_status')} note={video.get('note_status')} "
        + f"step={job.get('current_step')} progress={job.get('progress')}"
    )
    if line != last_line:
        print(line, flush=True)
        last_line = line
    if video.get("status") == "ready" and video.get("subtitle_status") == "ready":
        break
    if video.get("status") in {"failed", "missing"}:
        raise SystemExit(f"video={video_id} failed: stage={video.get('error_stage')} message={video.get('error_message')}")
    time.sleep(30)
else:
    raise SystemExit(f"video={video_id} timeout")

for path in [
    f"/api/videos/{video_id}/transcript",
    f"/api/videos/{video_id}/chapters",
    f"/api/videos/{video_id}/highlights",
    f"/api/videos/{video_id}/note",
]:
    with urllib.request.urlopen("http://127.0.0.1:8766" + path, timeout=30) as resp:
        body = resp.read()
    print(f"verify {path} http=200 bytes={len(body)}", flush=True)
print(f"video={video_id} complete", flush=True)
PY
  log "finished video=$VIDEO_ID"
done

log "all requested videos completed"
