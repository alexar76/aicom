#!/usr/bin/env bash
# Deploy DIOSCURI on the oracle host (203.0.113.20) from monorepo root.
#
# Same pattern as oracles/platon/lottery Gitea workflow:
#   1. mirror_to_gitea.sh dioscuri  — push satellite to Gitea#2 (HTTP + git-credentials)
#   2. ssh root@203.0.113.20       — git pull + docker compose on oracle
#
# Usage (from factory / any machine with passwordless ssh to oracle):
#   ./scripts/deploy_dioscuri_oracle.sh
#   RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh
#
# Env:
#   ORACLE_HOST          default root@203.0.113.20  (or `ssh oracle` after ~/.ssh/config)
#   ORACLE_DIOSCURI_DIR  default /root/dioscuri
#   SSH_BATCH_MODE       default yes — set no for interactive agent/password
#   SKIP_MIRROR=1        skip Gitea push (remote pull only)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="${ORACLE_HOST:-root@203.0.113.20}"
DIOSCURI_DIR="${ORACLE_DIOSCURI_DIR:-/root/dioscuri}"
GITEA_REPO="${GITEA_DIOSCURI_REPO:-ssh://git@gitea2/alexar76/dioscuri.git}"
HEALTH_URL="${ORACLE_DIOSCURI_HEALTH:-http://203.0.113.20:${DIOSCURI_HTTP_PORT:-8790}/health}"

SSH_OPTS=(-o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new)
if [[ "${SSH_BATCH_MODE:-yes}" == "yes" ]]; then
  SSH_OPTS+=(-o BatchMode=yes)
fi

echo "=== DIOSCURI oracle deploy ==="
echo "Oracle:  $ORACLE"
echo "App dir: $DIOSCURI_DIR"
echo ""

if [[ "${SKIP_MIRROR:-0}" != "1" ]]; then
  echo "--- 1/2 mirror dioscuri → Gitea#2 ---"
  "$ROOT/scripts/mirror_to_gitea.sh" dioscuri
else
  echo "--- 1/2 mirror skipped (SKIP_MIRROR=1) ---"
fi

echo ""
echo "--- 2/2 remote: git pull + docker compose ---"
ssh "${SSH_OPTS[@]}" "$ORACLE" \
  "DIOSCURI_DIR=$(printf '%q' "$DIOSCURI_DIR")" \
  "GITEA_REPO=$(printf '%q' "$GITEA_REPO")" \
  "RUN_CANON_SLOT=$(printf '%q' "${RUN_CANON_SLOT:-0}")" \
  'bash -s' <<'REMOTE'
set -euo pipefail

if [[ ! -d "${DIOSCURI_DIR}/.git" ]]; then
  echo "Cloning ${GITEA_REPO} → ${DIOSCURI_DIR}"
  git clone "${GITEA_REPO}" "${DIOSCURI_DIR}"
fi

cd "${DIOSCURI_DIR}"
git pull --ff-only

for f in .env dioscuri.config.json; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing ${DIOSCURI_DIR}/${f} on oracle — copy from .example and fill secrets" >&2
    exit 1
  fi
done

docker compose up -d --build
sleep 4
curl -sf "http://127.0.0.1:${DIOSCURI_HTTP_PORT:-8790}/health" | head -c 240 || true
echo

if [[ "${RUN_CANON_SLOT}" == "1" ]]; then
  echo "=== canon slot (one-shot) ==="
  DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
fi

echo "Remote OK"
REMOTE

echo ""
echo "--- health (from factory) ---"
curl -sf --max-time 8 "$HEALTH_URL" | head -c 240 || echo "WARN: could not reach $HEALTH_URL"
echo
echo "Deploy complete"
