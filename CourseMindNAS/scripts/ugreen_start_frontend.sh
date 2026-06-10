#!/usr/bin/env sh
set -eu

SRC_DIR="/app/frontend-src"
WORK_DIR="/runtime/frontend-work"
NPM_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"

mkdir -p "$WORK_DIR"
rm -rf "$WORK_DIR/src"

cp "$SRC_DIR/package.json" "$WORK_DIR/package.json"
cp "$SRC_DIR/package-lock.json" "$WORK_DIR/package-lock.json"
cp "$SRC_DIR/index.html" "$WORK_DIR/index.html"
cp "$SRC_DIR/tsconfig.json" "$WORK_DIR/tsconfig.json"
cp "$SRC_DIR/vite.config.ts" "$WORK_DIR/vite.config.ts"
cp -a "$SRC_DIR/src" "$WORK_DIR/src"

cd "$WORK_DIR"

npm ci --registry="$NPM_REGISTRY"

exec npm run dev -- --host 0.0.0.0 --port 3000
