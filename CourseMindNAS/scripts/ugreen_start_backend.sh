#!/usr/bin/env sh
set -eu

cd /app/backend

VENV_DIR="${BACKEND_VENV_DIR:-/runtime/backend-venv}"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

. "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip -i "$PIP_INDEX"
python -m pip install -r requirements.txt -i "$PIP_INDEX"

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
