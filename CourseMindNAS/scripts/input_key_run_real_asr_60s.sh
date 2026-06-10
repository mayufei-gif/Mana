#!/usr/bin/env sh
set -eu

cd "$HOME/coursemind-nas"

echo "Input DashScope API Key. It will not be displayed."
printf "DASHSCOPE_API_KEY: "
stty -echo
read DASH_KEY
stty echo
printf '\n'

if [ -z "$DASH_KEY" ]; then
  echo "[STOP] Empty key."
  exit 1
fi

cp .env ".env.bak.before_set_dashscope_key_$(date +%Y%m%d_%H%M%S)"

if grep -q '^DASHSCOPE_API_KEY=' .env; then
  sed -i "s|^DASHSCOPE_API_KEY=.*|DASHSCOPE_API_KEY=$DASH_KEY|" .env
else
  echo "DASHSCOPE_API_KEY=$DASH_KEY" >> .env
fi

unset DASH_KEY

echo "[OK] Key saved to .env. Starting 60-second real ASR sample verification."
bash "$HOME/coursemind-nas/scripts/run_real_asr_60s.sh"
