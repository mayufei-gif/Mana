#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${REGISTRY_PREFIX:?Set REGISTRY_PREFIX, for example registry.cn-hangzhou.aliyuncs.com/your_namespace}"

TAG="${TAG:-$(date +%Y%m%d_%H%M%S)}"
BACKEND_IMAGE="${BACKEND_IMAGE:-$REGISTRY_PREFIX/coursemind-backend:$TAG}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-$REGISTRY_PREFIX/coursemind-frontend:$TAG}"

docker build -t "$BACKEND_IMAGE" ./backend
docker build -t "$FRONTEND_IMAGE" ./frontend

docker push "$BACKEND_IMAGE"
docker push "$FRONTEND_IMAGE"

printf 'COURSEMIND_BACKEND_IMAGE=%s\n' "$BACKEND_IMAGE"
printf 'COURSEMIND_FRONTEND_IMAGE=%s\n' "$FRONTEND_IMAGE"
printf '\nOn NAS, run:\n'
printf '  export COURSEMIND_BACKEND_IMAGE=%q\n' "$BACKEND_IMAGE"
printf '  export COURSEMIND_FRONTEND_IMAGE=%q\n' "$FRONTEND_IMAGE"
printf '  sudo -E COMPOSE_FILE=docker-compose.registry.yml bash scripts/nas_verify.sh\n'
