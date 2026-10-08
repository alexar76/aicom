#!/bin/bash
# Install (or update) WARDEN's weekly ERC-8004 feedback refresh on admin-vps, from the monorepo.
#
#   deploy/erc-8004/install_refresh.sh [ssh-target]      # default admin-vps
#
# Puts the runner in /opt/warden-feedback with its own venv and a pinned @aimarket/warden, the
# state in /var/lib/warden-feedback (never overwritten), reports in /var/www/warden-feedback
# (served by the histor.modelmarket.dev vhost at /.well-known/erc-8004/feedback/), and enables
# warden-feedback.timer (Mondays 09:00 UTC, catches up after downtime). The wallet key is created
# on the host the first time (/etc/warden-feedback/wallet.json, 600) and never leaves it.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SRC/../.." && pwd)"
HOST=${1:-admin-vps}
WARDEN_VERSION=0.8.2
ssh "$HOST" 'mkdir -p /opt/warden-feedback/node /var/lib/warden-feedback /var/www/warden-feedback /etc/warden-feedback && chmod 700 /etc/warden-feedback'
scp -q "$SRC/feedback.py" "$SRC/register.py" "$SRC/build.py" "$SRC/warden_scan.mjs" "$SRC/warden_feedback_refresh.sh" "$SRC/requirements.lock" \
       "$ROOT/warden/scripts/mcp-survey/mcpclient.py" "$HOST:/opt/warden-feedback/"
scp -q "$SRC/warden-feedback.service" "$SRC/warden-feedback.timer" "$HOST:/etc/systemd/system/"
ssh "$HOST" "set -e; cd /opt/warden-feedback; chmod +x warden_feedback_refresh.sh
  [ -x .venv/bin/python ] || python3 -m venv .venv
  # Hash-locked: this venv signs with the feedback wallet. Regenerate the lock with
  #   uv pip compile <pins> --generate-hashes --python-version 3.12 -o deploy/erc-8004/requirements.lock
  .venv/bin/pip install -q --disable-pip-version-check --require-hashes -r requirements.lock
  cd node; [ -f package.json ] || npm init -y >/dev/null; npm install --silent --no-audit --no-fund '@aimarket/warden@$WARDEN_VERSION'
  [ -f /var/lib/warden-feedback/feedback-exclude.json ] || echo '[19151]' > /var/lib/warden-feedback/feedback-exclude.json
  if [ ! -f /etc/warden-feedback/wallet.json ]; then umask 077; /opt/warden-feedback/.venv/bin/python -c '
import json, secrets
from eth_account import Account
k = \"0x\" + secrets.token_hex(32)
json.dump({\"accounts\": [{\"address\": Account.from_key(k).address, \"private_key\": k}]}, open(\"/etc/warden-feedback/wallet.json\", \"w\"))'; fi
  chmod 600 /etc/warden-feedback/wallet.json
  systemctl daemon-reload; systemctl enable --now warden-feedback.timer >/dev/null
  systemctl list-timers warden-feedback.timer --no-pager | head -2"
