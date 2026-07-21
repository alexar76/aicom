#!/usr/bin/env bash
# One-time: allow factory VPS (5.129.212.122) to SSH to oracle (78.17.126.214) without password.
#
# Run this IN YOUR INTERACTIVE TERMINAL (where `ssh root@78.17.126.214` already works):
#   ./scripts/bootstrap_oracle_ssh.sh
#
# It uses your forwarded SSH agent to append the factory public key to oracle authorized_keys.
set -euo pipefail

ORACLE="${ORACLE_HOST:-root@78.17.126.214}"
PUBKEY_FILE="${PUBKEY_FILE:-/root/.ssh/id_ed25519.pub}"

if [[ ! -f "$PUBKEY_FILE" ]]; then
  echo "Missing $PUBKEY_FILE" >&2
  exit 1
fi

PUBKEY="$(cat "$PUBKEY_FILE")"
MARKER="github_deploy_20260224_1829"

echo "Adding factory pubkey to $ORACLE (marker: $MARKER) ..."
ssh "$ORACLE" "grep -q '$MARKER' /root/.ssh/authorized_keys 2>/dev/null || echo '$PUBKEY' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys"

echo "Verify from factory (non-interactive):"
ssh -o BatchMode=yes "$ORACLE" 'hostname && echo OK'

echo "Bootstrap done — Cursor agent can now: ssh root@78.17.126.214"
