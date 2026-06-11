#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${OPENCLAW_CONTAINER:-openclaw-gateway-1}"
PATCH_LOCAL="${1:-$(dirname "$0")/patch_openclaw_dynamic_channels.cjs}"
PATCH_IN_CONTAINER="/tmp/patch_openclaw_dynamic_channels.cjs"

if [ ! -f "$PATCH_LOCAL" ]; then
  echo "[RED] patch file not found: $PATCH_LOCAL" >&2
  exit 1
fi

if docker ps >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker ps >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "[YELLOW] docker requires sudo. The next sudo prompt is expected; no password will be stored." >&2
  DOCKER=(sudo docker)
fi

echo "== verify OpenClaw container =="
"${DOCKER[@]}" ps --format '{{.Names}}' | grep -Fx "$CONTAINER"

echo "== upload patch into container =="
"${DOCKER[@]}" cp "$PATCH_LOCAL" "$CONTAINER:$PATCH_IN_CONTAINER"

echo "== apply dynamic channel patch =="
"${DOCKER[@]}" exec "$CONTAINER" node "$PATCH_IN_CONTAINER"

echo "== restart OpenClaw container =="
"${DOCKER[@]}" restart "$CONTAINER"

echo "== verify patch marker =="
"${DOCKER[@]}" exec "$CONTAINER" sh -lc "grep -n 'MANA_OPENCLAW_DYNAMIC_CHANNELS_PATCH_V1' /root/.openclaw/extensions/openclaw-weixin/dist/src/messaging/slash-commands.js | head"

echo "[GREEN] OpenClaw dynamic slash channels patch installed."
