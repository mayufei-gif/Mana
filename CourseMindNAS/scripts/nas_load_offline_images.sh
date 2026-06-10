#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_TAR="${1:-}"

if [ -z "$IMAGE_TAR" ]; then
  IMAGE_TAR="$(find "$ROOT" -maxdepth 4 -type f -name 'coursemind_offline_images_*.tar' 2>/dev/null | sort | tail -1)"
fi

if [ -z "$IMAGE_TAR" ] || [ ! -f "$IMAGE_TAR" ]; then
  echo "[FAIL] offline image tar not found. Put coursemind_offline_images_*.tar under this project or pass it as argv[1]." >&2
  exit 1
fi

docker load -i "$IMAGE_TAR"
COMPOSE_FILE=docker-compose.offline.yml bash scripts/nas_verify.sh
