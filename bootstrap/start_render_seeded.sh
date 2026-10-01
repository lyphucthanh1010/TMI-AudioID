#!/bin/sh
set -eu

POT_PID=""
if [ -f /opt/bgutil/server/build/main.js ]; then
  node /opt/bgutil/server/build/main.js --host 127.0.0.1 --port 4416 >/tmp/bgutil-pot.log 2>&1 &
  POT_PID=$!
  i=0
  while [ "$i" -lt 30 ]; do
    if curl -fsS --max-time 1 http://127.0.0.1:4416/ping >/dev/null 2>&1; then
      echo "[pot-provider] ready on 127.0.0.1:4416"
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  if [ "$i" -ge 30 ]; then
    echo "[pot-provider] warning: provider did not become ready"
    cat /tmp/bgutil-pot.log 2>/dev/null || true
  fi
fi

python /app/bootstrap/seed_test_account.py /app/pretrained_runtime/audioid.db

if [ -f /runtime/audioid.db ]; then
  python /app/bootstrap/seed_test_account.py /runtime/audioid.db
fi

exec /app/backend/scripts/start_render.sh
