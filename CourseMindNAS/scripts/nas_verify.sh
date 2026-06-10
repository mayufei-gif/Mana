#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_BASE="${API_BASE:-http://127.0.0.1:8766}"
FRONTEND_BASE="${FRONTEND_BASE:-http://127.0.0.1:8788}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKEND_PYTHON="${BACKEND_PYTHON:-python}"
TEST_REL_DIR="测试课程/初级会计"
TEST_FILE="001.零基础入门（一）_mock测试.mp4"

ok() {
  printf '[OK] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 not found"
}

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$@"
}

wait_http() {
  url="$1"
  label="$2"
  expected_pattern="$3"
  attempts="${4:-120}"
  for _ in $(seq 1 "$attempts"); do
    code="$(http_code "$url" || true)"
    if printf '%s\n' "$code" | grep -Eq "$expected_pattern"; then
      ok "$label: $code"
      return 0
    fi
    sleep 2
  done
  fail "$label failed: last http code $code"
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

compose_up() {
  if grep -Eq '^[[:space:]]*build:' "$COMPOSE_FILE"; then
    compose up --build -d
  else
    compose up -d
  fi
}

mkdir -p CourseMind/videos CourseMind/upload-videos CourseMind/data CourseMind/processed CourseMind/logs CourseMind/config
cp -f config/domain_terms.json CourseMind/config/domain_terms.json 2>/dev/null || true
cp -f config/correction_terms.json CourseMind/config/correction_terms.json 2>/dev/null || true

need_cmd docker
need_cmd curl

[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"
ok "compose file: $COMPOSE_FILE"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    ok "created .env from .env.example"
  elif [ -f env.example ]; then
    cp env.example .env
    ok "created .env from env.example"
  else
    fail ".env missing and no .env.example/env.example template found"
  fi
fi

grep -Eq '^ASR_PROVIDER=mock$' .env || fail ".env must set ASR_PROVIDER=mock for this mock verification"
grep -Eq '^TRANSCRIPTION_PROVIDER=mock$' .env || fail ".env must set TRANSCRIPTION_PROVIDER=mock for this mock verification"
grep -Eq '^AUTO_PROCESS_NEW_VIDEO=false$' .env || fail ".env must keep AUTO_PROCESS_NEW_VIDEO=false"
ok "safe env checked"

compose_up || {
  compose ps || true
  compose logs --tail=200 backend || true
  compose logs --tail=200 frontend || true
  fail "docker compose up failed"
}
ok "docker compose up"

compose ps
compose logs --tail=80 backend || true
compose logs --tail=80 frontend || true

compose exec -T backend ffmpeg -version >/tmp/coursemind_ffmpeg_check.txt
ok "ffmpeg available"

if [ "$BACKEND_PYTHON" != "python" ]; then
  python_ready=0
  for _ in $(seq 1 120); do
    if compose exec -T backend sh -lc "test -x '$BACKEND_PYTHON'"; then
      python_ready=1
      break
    fi
    sleep 2
  done
  [ "$python_ready" = "1" ] || fail "backend python not ready: $BACKEND_PYTHON"
  ok "backend python ready: $BACKEND_PYTHON"
fi

SETTINGS_OUTPUT="$(compose exec -T backend "$BACKEND_PYTHON" - <<'PY'
from app.config import settings
print(settings.video_dir, settings.data_dir, settings.storage_dir, settings.log_dir, settings.config_dir)
PY
)"
printf '%s\n' "$SETTINGS_OUTPUT"
printf '%s\n' "$SETTINGS_OUTPUT" | grep -q '/videos' || fail "settings.video_dir is not /videos"
printf '%s\n' "$SETTINGS_OUTPUT" | grep -q '/data' || fail "settings.data_dir is not /data"
printf '%s\n' "$SETTINGS_OUTPUT" | grep -q '/processed' || fail "settings.storage_dir is not /processed"
printf '%s\n' "$SETTINGS_OUTPUT" | grep -q '/logs' || fail "settings.log_dir is not /logs"
printf '%s\n' "$SETTINGS_OUTPUT" | grep -q '/config' || fail "settings.config_dir is not /config"
ok "settings paths"

compose exec -T backend sh -lc "test -r /videos && test -w /data && test -w /processed && test -w /logs && test -w /config"
compose exec -T backend sh -lc "echo ok > /data/write_test.txt && echo ok > /processed/write_test.txt && echo ok > /logs/write_test.txt && echo ok > /config/write_test.txt"
ok "directory permissions"

compose exec -T backend "$BACKEND_PYTHON" - <<'PY'
import sqlite3
p = "/data/sqlite_test.db"
conn = sqlite3.connect(p)
conn.execute("create table if not exists t(id integer primary key, name text)")
conn.execute("insert into t(name) values('ok')")
conn.commit()
print("sqlite rows:", conn.execute("select count(*) from t").fetchone()[0])
conn.close()
PY
ok "sqlite writable"

wait_http "$API_BASE/healthz" "backend healthz" '^200$' 120
wait_http "$FRONTEND_BASE" "frontend reachable" '^(200|301|302|304)$' 120

compose run --rm --no-deps -T \
  -v "$ROOT/CourseMind/videos:/tmp/videos" \
  backend sh -lc "mkdir -p '/tmp/videos/$TEST_REL_DIR' && ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=25 -f lavfi -i sine=frequency=1000:sample_rate=44100 -t 5 -c:v libx264 -c:a aac '/tmp/videos/$TEST_REL_DIR/$TEST_FILE' >/tmp/ffmpeg_create.log 2>&1"
ok "chinese mock video created"

curl -fsS -X POST "$API_BASE/api/videos/scan" \
  -H 'Content-Type: application/json' \
  -d '{}' >/tmp/coursemind_scan.json
cat /tmp/coursemind_scan.json
ok "scan api"

VIDEO_ID="$(compose exec -T backend "$BACKEND_PYTHON" - <<'PY'
from app import database
database.init_db()
row = database.fetch_one("SELECT id FROM videos WHERE title LIKE ? ORDER BY id DESC LIMIT 1", ("%mock测试%",))
print(row["id"] if row else "")
PY
)"
[ -n "$VIDEO_ID" ] || fail "mock video not found in database"
ok "mock video id: $VIDEO_ID"

compose exec -T backend "$BACKEND_PYTHON" - "$VIDEO_ID" <<'PY'
import sys
from app import database
video_id = int(sys.argv[1])
database.execute("UPDATE videos SET status='pending', subtitle_status='none', analysis_status='none', note_status='none' WHERE id=?", (video_id,))
PY

NOT_READY_CODE="$(http_code "$API_BASE/api/videos/$VIDEO_ID/stream")"
[ "$NOT_READY_CODE" = "409" ] || fail "not-ready stream expected 409, got $NOT_READY_CODE"
ok "not-ready stream gating"

curl -fsS -X POST "$API_BASE/api/videos/$VIDEO_ID/process" >/tmp/coursemind_process.json
cat /tmp/coursemind_process.json
ok "manual process queued"

for _ in $(seq 1 60); do
  STATUS="$(compose exec -T backend "$BACKEND_PYTHON" - "$VIDEO_ID" <<'PY'
import sys
from app import database
video_id = int(sys.argv[1])
row = database.fetch_one("SELECT status, subtitle_status, analysis_status, note_status, error_stage, error_message FROM videos WHERE id=?", (video_id,))
print("|".join(str(row.get(k) or "") for k in ("status", "subtitle_status", "analysis_status", "note_status", "error_stage", "error_message")))
PY
)"
  printf 'status=%s\n' "$STATUS"
  case "$STATUS" in
    ready\|ready\|ready\|ready\|*) break ;;
    failed*|missing*) fail "processing failed: $STATUS" ;;
  esac
  sleep 2
done
printf '%s\n' "$STATUS" | grep -q '^ready|ready|' || fail "video did not become ready"
ok "mock processing ready"

compose exec -T backend sh -lc "find /processed -maxdepth 5 -type f | sort | head -100"

compose exec -T backend "$BACKEND_PYTHON" - "$VIDEO_ID" <<'PY'
import json
import sys
from pathlib import Path
video_id = sys.argv[1]
base = Path("/processed")
clean = base / "transcripts" / video_id / "clean_transcript.json"
smart_vtt = base / "subtitles" / video_id / "smart_subtitle.vtt"
smart_srt = base / "subtitles" / video_id / "smart_subtitle.srt"
note = base / "notes" / video_id / "note.md"
for path in (clean, smart_vtt, smart_srt, note):
    print(path, path.exists())
    if not path.exists():
        raise SystemExit(f"missing {path}")
payload = json.loads(clean.read_text(encoding="utf-8"))
print("segments:", len(payload.get("segments") or []))
print("subtitle_segments:", len(payload.get("subtitle_segments") or []))
if not payload.get("segments") or not payload.get("subtitle_segments"):
    raise SystemExit("clean_transcript must contain segments and subtitle_segments")
PY
ok "processed artifacts"

READY_CODE="$(http_code "$API_BASE/api/videos/$VIDEO_ID/stream")"
case "$READY_CODE" in
  200|206) ok "ready stream: $READY_CODE" ;;
  *) fail "ready stream expected 200/206, got $READY_CODE" ;;
esac

for endpoint in transcript chapters highlights note; do
  case "$endpoint" in
    transcript) path="$API_BASE/api/videos/$VIDEO_ID/transcript" ;;
    *) path="$API_BASE/api/videos/$VIDEO_ID/$endpoint" ;;
  esac
  curl -fsS "$path" >/tmp/coursemind_${endpoint}.json
  test -s /tmp/coursemind_${endpoint}.json || fail "$endpoint endpoint returned empty"
  ok "$endpoint endpoint"
done

printf '\nNAS Docker mock verification report\n'
printf 'Docker build/up: passed\n'
printf 'backend healthz: passed\n'
printf 'frontend reachable: passed\n'
printf 'ffmpeg: passed\n'
printf 'settings paths: %s\n' "$SETTINGS_OUTPUT"
printf 'directory permissions: passed\n'
printf 'SQLite persistence: passed\n'
printf 'Chinese path scan: passed\n'
printf 'mock processing: passed\n'
printf 'stream gating: passed\n'
printf 'real ASR called: no\n'
printf 'AUTO_PROCESS_NEW_VIDEO=false: yes\n'
