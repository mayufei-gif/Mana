#!/usr/bin/env sh
set -eu

cd "$HOME/coursemind-nas"

SAMPLE_ID="${1:-9}"

if ! grep -q 'recognition.call' backend/app/services/transcription/aliyun_dashscope_provider.py; then
  echo "[STOP] NAS has not synced the DashScope local-file call provider yet."
  echo "[STOP] Wait for sync, then run again:"
  echo "       grep -n 'recognition.call' backend/app/services/transcription/aliyun_dashscope_provider.py"
  exit 1
fi

if ! grep -q 'def _prepare_dashscope_audio' backend/app/services/transcription/aliyun_dashscope_provider.py; then
  echo "[STOP] NAS has not synced the DashScope audio normalize helper yet."
  echo "[STOP] Wait for sync, then run again:"
  echo "       grep -n 'def _prepare_dashscope_audio' backend/app/services/transcription/aliyun_dashscope_provider.py"
  exit 1
fi

if ! grep -q 'def _safe_getattr' backend/app/services/transcription/aliyun_dashscope_provider.py; then
  echo "[STOP] NAS has not synced the DashScope KeyError('text') callback fix yet."
  echo "[STOP] Wait for sync, then run again:"
  echo "       grep -n 'def _safe_getattr' backend/app/services/transcription/aliyun_dashscope_provider.py"
  exit 1
fi

if ! grep -q 'def _is_better_sentence' backend/app/services/transcription/aliyun_dashscope_provider.py; then
  echo "[STOP] NAS has not synced the DashScope partial-sentence dedupe fix yet."
  echo "[STOP] Wait for sync, then run again:"
  echo "       grep -n 'def _is_better_sentence' backend/app/services/transcription/aliyun_dashscope_provider.py"
  exit 1
fi

if ! grep -q 'key == "end_time" and "start_time"' backend/app/services/transcription/base.py; then
  echo "[STOP] NAS has not synced the patched ASR time-unit parser yet."
  echo "[STOP] Wait for sync, then run again:"
  echo "       grep -n 'start_time' backend/app/services/transcription/base.py"
  exit 1
fi

if ! grep -Eq '^(DASHSCOPE_API_KEY|TRANSCRIPTION_API_KEY)=.+' .env; then
  echo "[STOP] Missing DASHSCOPE_API_KEY or TRANSCRIPTION_API_KEY in .env."
  echo "[STOP] Run scripts/input_key_run_real_asr_60s.sh first."
  exit 1
fi

BACKUP_ENV=".env.bak.before_retry_real_asr_sample_${SAMPLE_ID}_$(date +%Y%m%d_%H%M%S)"
cp .env "$BACKUP_ENV"

restore_env() {
  echo "[RESTORE] Restore .env and restart CourseMind."
  cp "$BACKUP_ENV" .env
  sudo docker compose -f docker-compose.ugreen-local.yml down
  sudo docker compose -f docker-compose.ugreen-local.yml up -d
}
trap restore_env EXIT

set_env_kv() {
  key="$1"
  value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

wait_backend() {
  echo "== wait backend health =="
  for i in $(seq 1 90); do
    if curl -fsS http://127.0.0.1:8766/healthz >/dev/null 2>&1; then
      echo "backend ready"
      return 0
    fi
    sleep 2
  done
  echo "[STOP] backend health check timeout"
  return 1
}

echo "== 1. verify sample exists =="
curl -s "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/status" | python3 -m json.tool | head -80

echo "== 2. temporarily switch to DashScope fun-asr-realtime =="
set_env_kv AUTO_PROCESS_NEW_VIDEO false
set_env_kv AUTO_PROCESS_NEW_VIDEOS false
set_env_kv ASR_PROVIDER aliyun_dashscope
set_env_kv TRANSCRIPTION_PROVIDER aliyun_dashscope
set_env_kv ASR_MODEL fun-asr-realtime
set_env_kv TRANSCRIPTION_MODEL fun-asr-realtime
set_env_kv AUDIO_CHUNK_SECONDS 60
set_env_kv MAX_SINGLE_VIDEO_MINUTES 2

sudo docker compose -f docker-compose.ugreen-local.yml down
sudo docker compose -f docker-compose.ugreen-local.yml up -d
wait_backend

curl -s -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false}'
printf '\n'

echo "== 3. reprocess only sample ${SAMPLE_ID} =="
curl -s -X POST "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/reprocess"
printf '\n'

echo "== 4. wait until ready =="
python3 - "$SAMPLE_ID" <<'PY'
import json
import sys
import time
import urllib.request

video_id = sys.argv[1]
deadline = time.time() + 1200
while time.time() < deadline:
    with urllib.request.urlopen(f"http://127.0.0.1:8766/api/videos/{video_id}/status", timeout=10) as resp:
        payload = json.load(resp)
    video = payload["data"]["video"]
    job = payload["data"].get("job") or {}
    print(
        time.strftime("%H:%M:%S"),
        "video=", video.get("status"),
        "subtitle=", video.get("subtitle_status"),
        "stage=", video.get("error_stage"),
        "step=", job.get("current_step"),
        "progress=", job.get("progress"),
    )
    if video.get("status") == "ready" and video.get("subtitle_status") == "ready":
        sys.exit(0)
    if video.get("status") in {"failed", "missing"}:
        raise SystemExit(f"Failed: stage={video.get('error_stage')} message={video.get('error_message')}")
    time.sleep(5)
raise SystemExit("Timeout")
PY

echo "== 5. verify outputs =="
curl -s -L -o /dev/null -w "stream http=%{http_code} bytes=%{size_download} type=%{content_type}\n" -r 0-0 "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/stream"
curl -s -L -o /dev/null -w "transcript http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/transcript"
curl -s -L -o /dev/null -w "smart_vtt http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/smart-subtitle/vtt"
curl -s -L -o /dev/null -w "smart_srt http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/smart-subtitle/srt"
curl -s -L -o /dev/null -w "chapters http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/chapters"
curl -s -L -o /dev/null -w "highlights http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/highlights"
curl -s -L -o /dev/null -w "note http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/note"

echo "== 6. final status =="
curl -s "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/status" | python3 -m json.tool | head -120

echo "== 7. ASR debug logs if any =="
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend sh -lc 'ls -lh /logs/dashscope_asr_debug_*.json 2>/dev/null | tail -5 || true'

echo "[OK] retry finished."
