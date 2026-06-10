#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PYTHON=/runtime/backend-venv/bin/python \
COMPOSE_FILE=docker-compose.ugreen-local.yml \
bash scripts/nas_verify.sh
