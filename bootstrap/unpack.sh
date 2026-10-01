#!/bin/sh
set -eu

ROOT="${1:-.}"
BOOTSTRAP_DIR="${ROOT}/bootstrap"

echo "[bootstrap] unpacking source"
base64 -d "${BOOTSTRAP_DIR}/source.b64" > /tmp/tmi-source.tar.gz
tar -xzf /tmp/tmi-source.tar.gz -C "${ROOT}"
rm -f /tmp/tmi-source.tar.gz

if ls "${BOOTSTRAP_DIR}"/db.part*.b64 >/dev/null 2>&1; then
  echo "[bootstrap] reconstructing pretrained seed database"
  mkdir -p "${ROOT}/backend/runtime"
  cat "${BOOTSTRAP_DIR}"/db.part*.b64 | base64 -d > /tmp/audioid.db.xz
  xz -dc /tmp/audioid.db.xz > "${ROOT}/backend/runtime/audioid.db"
  rm -f /tmp/audioid.db.xz
fi

echo "[bootstrap] done"
