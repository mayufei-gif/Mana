#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${COURSEMIND_BACKEND_IMAGE:?Set COURSEMIND_BACKEND_IMAGE}"
: "${COURSEMIND_FRONTEND_IMAGE:?Set COURSEMIND_FRONTEND_IMAGE}"

docker pull "$COURSEMIND_BACKEND_IMAGE"
docker pull "$COURSEMIND_FRONTEND_IMAGE"

COMPOSE_FILE=docker-compose.registry.yml bash scripts/nas_verify.sh
