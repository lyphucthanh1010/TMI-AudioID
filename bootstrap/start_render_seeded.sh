#!/bin/sh
set -eu

python /app/bootstrap/seed_test_account.py /app/pretrained_runtime/audioid.db

if [ -f /runtime/audioid.db ]; then
  python /app/bootstrap/seed_test_account.py /runtime/audioid.db
fi

exec /app/backend/scripts/start_render.sh
