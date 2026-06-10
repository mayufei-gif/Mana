#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${OUT_DIR:-$ROOT/CourseMind/images}"
STAMP="$(date +%Y%m%d_%H%M%S)"
IMAGE_TAR="${IMAGE_TAR:-$OUT_DIR/coursemind_offline_images_$STAMP.tar}"

mkdir -p "$OUT_DIR"

docker build -t coursemind-backend:offline ./backend
docker build -t coursemind-frontend:offline ./frontend
docker save -o "$IMAGE_TAR" coursemind-backend:offline coursemind-frontend:offline

printf 'Offline images saved: %s\n' "$IMAGE_TAR"
printf 'Copy this tar to the NAS project, then run:\n'
printf '  sudo docker load -i "%s"\n' "$IMAGE_TAR"
printf '  sudo COMPOSE_FILE=docker-compose.offline.yml bash scripts/nas_verify.sh\n'
