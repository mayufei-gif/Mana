#!/usr/bin/env sh
set -eu

PATCH_TAR="${1:-}"
if [ -z "$PATCH_TAR" ]; then
  PATCH_TAR="$(find "$(pwd)" -maxdepth 1 -type f -name 'coursemind-dashscope-local-file-asr-fix_20260606_2046.tar' 2>/dev/null | sort | tail -1)"
fi
if [ -z "$PATCH_TAR" ] || [ ! -f "$PATCH_TAR" ]; then
  echo "[STOP] Patch tar not found."
  exit 1
fi

find_project() {
  if [ -f "$HOME/coursemind-nas/docker-compose.ugreen-local.yml" ]; then
    printf '%s\n' "$HOME/coursemind-nas"
    return 0
  fi
  find /home/yma648692gmail.com -maxdepth 8 -type f -name 'docker-compose.ugreen-local.yml' 2>/dev/null \
    | grep 'coursemind-nas/docker-compose.ugreen-local.yml$' \
    | sed 's#/docker-compose.ugreen-local.yml$##' \
    | sort \
    | tail -1
}

PROJECT_DIR="$(find_project)"
if [ -z "$PROJECT_DIR" ] || [ ! -f "$PROJECT_DIR/docker-compose.ugreen-local.yml" ]; then
  echo "[STOP] Could not locate running CourseMind project."
  exit 1
fi

cd "$PROJECT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="CourseMind/backups/dashscope_local_file_asr_fix_$STAMP"
mkdir -p "$BACKUP_DIR"

echo "== 1. project =="
pwd

echo "== 2. backup files =="
for f in \
  backend/app/services/transcription/aliyun_dashscope_provider.py \
  scripts/retry_real_asr_sample_9.sh
do
  if [ -f "$f" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp "$f" "$BACKUP_DIR/$f"
  fi
done
echo "$BACKUP_DIR"

echo "== 3. apply patch =="
tar -tf "$PATCH_TAR"
tar -xf "$PATCH_TAR" -C "$PROJECT_DIR"
chmod +x scripts/run_real_asr_60s.sh scripts/retry_real_asr_sample_9.sh || true

echo "== 4. verify patched markers =="
grep -n 'recognition.call' backend/app/services/transcription/aliyun_dashscope_provider.py
grep -n 'def _prepare_dashscope_audio' backend/app/services/transcription/aliyun_dashscope_provider.py
grep -n 'callback=callback' backend/app/services/transcription/aliyun_dashscope_provider.py

echo "== 5. compile backend file without writing __pycache__ =="
sudo docker compose -f docker-compose.ugreen-local.yml exec -T backend python3 - <<'PY'
from pathlib import Path
for p in [
    Path('/app/backend/app/services/transcription/aliyun_dashscope_provider.py'),
    Path('/app/backend/app/services/transcription/base.py'),
]:
    compile(p.read_text(encoding='utf-8'), str(p), 'exec')
    print('syntax ok:', p)
PY

echo "== 6. restart backend =="
sudo docker compose -f docker-compose.ugreen-local.yml restart backend

echo "== 7. wait backend health =="
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8766/healthz >/dev/null 2>&1; then
    echo "[OK] backend ready"
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "[STOP] backend health timeout"
    exit 1
  fi
  sleep 2
done

echo "== 8. verify safe mode before ASR sample =="
grep -E '^(AUTO_PROCESS_NEW_VIDEO|ASR_PROVIDER|TRANSCRIPTION_PROVIDER|ASR_MODEL|TRANSCRIPTION_MODEL)=' .env || true

echo "== 9. run one 60-second real ASR sample =="
echo "This script keeps AUTO_PROCESS_NEW_VIDEO=false and restores .env after the sample run."
bash scripts/run_real_asr_60s.sh
