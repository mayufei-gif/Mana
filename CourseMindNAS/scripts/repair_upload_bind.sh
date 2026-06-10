#!/usr/bin/env sh
set -eu

cd "$HOME/coursemind-nas"

OLD_HOST="/home/yma648692gmail.com/电脑备份文件/工作项目文件/NAS视频字幕/视频"

echo "== 1. backup .env and database =="
cp .env ".env.bak.before_repair_upload_bind_$(date +%Y%m%d_%H%M%S)"
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend sh -lc 'cp /data/coursemind.db /data/coursemind_backup_before_repair_upload_bind_$(date +%Y%m%d_%H%M%S).db && ls -lh /data/coursemind_backup_before_repair_upload_bind_*.db | tail -3'

echo "== 2. restore stable video mounts =="
grep -q '^HOST_VIDEO_ROOT=' .env && sed -i "s|^HOST_VIDEO_ROOT=.*|HOST_VIDEO_ROOT=$OLD_HOST|" .env || echo "HOST_VIDEO_ROOT=$OLD_HOST" >> .env
grep -q '^HOST_UPLOAD_VIDEO_ROOT=' .env && sed -i "s|^HOST_UPLOAD_VIDEO_ROOT=.*|HOST_UPLOAD_VIDEO_ROOT=$OLD_HOST|" .env || echo "HOST_UPLOAD_VIDEO_ROOT=$OLD_HOST" >> .env
grep -q '^AUTO_PROCESS_NEW_VIDEO=' .env && sed -i 's|^AUTO_PROCESS_NEW_VIDEO=.*|AUTO_PROCESS_NEW_VIDEO=false|' .env || echo 'AUTO_PROCESS_NEW_VIDEO=false' >> .env
grep -q '^ASR_PROVIDER=' .env && sed -i 's|^ASR_PROVIDER=.*|ASR_PROVIDER=mock|' .env || echo 'ASR_PROVIDER=mock' >> .env
grep -q '^TRANSCRIPTION_PROVIDER=' .env && sed -i 's|^TRANSCRIPTION_PROVIDER=.*|TRANSCRIPTION_PROVIDER=mock|' .env || echo 'TRANSCRIPTION_PROVIDER=mock' >> .env

curl -s -X POST http://127.0.0.1:8766/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"auto_process_new_videos":false}'
printf '\n'

echo "== 3. restart CourseMind =="
sudo docker compose -f docker-compose.ugreen-local.yml down
sudo docker compose -f docker-compose.ugreen-local.yml up -d
sleep 8

echo "== 4. scan once =="
curl -s -X POST http://127.0.0.1:8766/api/videos/scan
printf '\n'

echo "== 5. repair ready states and remove /videos duplicates =="
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("/data/coursemind.db")
conn.row_factory = sqlite3.Row

print("before:")
for row in conn.execute("""
SELECT id, title, file_path, status, subtitle_status, missing
FROM videos
ORDER BY id
""").fetchall():
    print(dict(row))

conn.execute("""
UPDATE videos
SET status = CASE WHEN subtitle_status = 'ready' THEN 'ready' ELSE 'pending' END,
    missing = 0,
    error_stage = NULL,
    error_message = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE file_path LIKE '/videos_upload/%'
""")

conn.execute("""
DELETE FROM videos
WHERE file_path LIKE '/videos/%'
  AND EXISTS (
    SELECT 1
    FROM videos u
    WHERE u.file_path LIKE '/videos_upload/%'
      AND u.file_size = videos.file_size
      AND u.extension = videos.extension
  )
""")

conn.commit()

print("after:")
for row in conn.execute("""
SELECT id, title, file_path, status, subtitle_status, missing
FROM videos
ORDER BY id
""").fetchall():
    print(dict(row))

conn.close()
PY

echo "== 6. final scan =="
curl -s -X POST http://127.0.0.1:8766/api/videos/scan
printf '\n'

echo "== 7. current videos =="
curl -s http://127.0.0.1:8766/api/videos | python3 -m json.tool | head -180

echo "[OK] repair finished. Expected: only two /videos_upload videos, both ready."
