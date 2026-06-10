#!/usr/bin/env sh
set -eu

cd "$HOME/coursemind-nas"

# Only process a generated 60-second sample. Do not batch-process NAS videos.

if ! grep -Eq '^(DASHSCOPE_API_KEY|TRANSCRIPTION_API_KEY)=.+' .env; then
  echo "[STOP] Missing DASHSCOPE_API_KEY or TRANSCRIPTION_API_KEY in .env."
  echo "[STOP] Run scripts/input_key_run_real_asr_60s.sh first."
  exit 1
fi

BACKUP_ENV=".env.bak.before_real_asr_60s_$(date +%Y%m%d_%H%M%S)"
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

echo "== 1. keep auto processing disabled =="
curl -s -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false}'
printf '\n'

echo "== 2. create a 60-second sample in /processed/real_asr_samples =="
SAMPLE_PATH="$(
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend python3 - <<'PY'
import sqlite3
import subprocess
import time
from pathlib import Path

conn = sqlite3.connect("/data/coursemind.db")
conn.row_factory = sqlite3.Row
row = conn.execute("""
SELECT id, file_path
FROM videos
WHERE missing = 0
  AND file_path LIKE '/videos_upload/%'
  AND extension = '.mp4'
ORDER BY id DESC
LIMIT 1
""").fetchone()
conn.close()
if not row:
    raise SystemExit("No /videos_upload mp4 video found")

source = Path(row["file_path"])
out_dir = Path("/processed/real_asr_samples")
out_dir.mkdir(parents=True, exist_ok=True)
output = out_dir / f"real_asr_60s_{int(time.time())}.mp4"

cmd = [
    "ffmpeg", "-y",
    "-ss", "60",
    "-t", "60",
    "-i", str(source),
    "-map", "0:v:0?",
    "-map", "0:a:0?",
    "-c:v", "copy",
    "-c:a", "aac",
    "-ar", "16000",
    "-ac", "1",
    str(output),
]
proc = subprocess.run(cmd, capture_output=True, text=True)
if proc.returncode != 0:
    raise SystemExit(proc.stderr or proc.stdout or "ffmpeg sample failed")
print(output)
PY
)"
echo "SAMPLE_PATH=$SAMPLE_PATH"

echo "== 3. scan sample directory =="
curl -s -X POST http://127.0.0.1:8766/api/videos/scan \
  -H 'Content-Type: application/json' \
  -d '{"video_dir":"/processed/real_asr_samples"}'
printf '\n'

SAMPLE_ID="$(
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend python3 - "$SAMPLE_PATH" <<'PY'
import sqlite3
import sys

sample_path = sys.argv[1]
conn = sqlite3.connect("/data/coursemind.db")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT id FROM videos WHERE file_path = ? ORDER BY id DESC LIMIT 1", (sample_path,)).fetchone()
if not row:
    row = conn.execute("""
        SELECT id, file_path, created_at, updated_at
        FROM videos
        WHERE missing = 0
          AND file_path LIKE '/processed/real_asr_samples/%'
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()
conn.close()
if not row:
    raise SystemExit(f"Sample not found in DB after scan/dedupe: {sample_path}")
print(row["id"])
PY
)"
echo "SAMPLE_ID=$SAMPLE_ID"

echo "== 4. temporarily switch to DashScope fun-asr-realtime =="
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

echo "== 5. reprocess only the sample =="
curl -s -X POST "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/reprocess"
printf '\n'

echo "== 6. wait until ready =="
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

echo "== 7. verify outputs =="
curl -s -L -o /dev/null -w "stream http=%{http_code} bytes=%{size_download} type=%{content_type}\n" -r 0-0 "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/stream"
curl -s -L -o /dev/null -w "transcript http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/transcript"
curl -s -L -o /dev/null -w "smart_vtt http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/smart-subtitle/vtt"
curl -s -L -o /dev/null -w "smart_srt http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/smart-subtitle/srt"
curl -s -L -o /dev/null -w "chapters http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/chapters"
curl -s -L -o /dev/null -w "highlights http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/highlights"
curl -s -L -o /dev/null -w "note http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/note"

echo "== 8. final status =="
curl -s "http://127.0.0.1:8766/api/videos/${SAMPLE_ID}/status" | python3 -m json.tool | head -120

echo "[OK] 60-second real ASR sample verification finished."
