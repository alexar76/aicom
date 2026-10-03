#!/usr/bin/env bash
# Stand up the bubble's locally published provider (`uni.answer@v1`, deploy/uni-provider-example.py).
#
# The hub calls it at http://172.17.0.1:9195/invoke — the docker bridge address, because the
# hub container cannot reach the host's loopback. When UNI moved from my-vps to factory-vps
# on 2026-10-03 this provider did not move with it: on the new host nothing listened on
# 172.17.0.1:9195 and the firewall dropped the SYN, so every `uni.answer@v1` invoke hung on
# connect for longer than the realm buyer's 10 s timeout. That was the "Invoke error: timed
# out" on the first purchase of every round.
#
# The signing key is the provider's identity: the hub stores its public key with the
# capability and refuses responses signed by any other. Copy /var/lib/uni_provider_key from
# the old host BEFORE running this on a new one; without it a fresh key is generated and the
# capability has to be re-published with the new public key.
#
# Idempotent.
set -euo pipefail

REPO="${REPO:-/root/claudecode/aicom}"
PYTHON="${PYTHON:-/usr/bin/python3}"

if [[ ! -f /var/lib/uni_provider_key ]]; then
  echo "WARNING: /var/lib/uni_provider_key is missing — a NEW key will be generated and the" >&2
  echo "hub will refuse its signatures until uni.answer@v1 is re-published with it." >&2
fi

cat > /etc/systemd/system/uni-provider.service <<UNIT
[Unit]
Description=UNI bubble capability provider (Ed25519-signing)
After=network.target docker.service

[Service]
Type=simple
ExecStart=$PYTHON $REPO/deploy/uni-provider-example.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

# Containers may reach it; the internet may not (it binds the bridge address only, and the
# rule is scoped to the docker subnet like the bubble chain's).
if command -v ufw >/dev/null 2>&1; then
  ufw allow proto tcp from 172.17.0.0/16 to 172.17.0.1 port 9195 \
    comment 'uni-provider bubble, docker-only' >/dev/null
fi

systemctl daemon-reload
systemctl enable uni-provider >/dev/null
systemctl restart uni-provider

for _ in $(seq 1 20); do
  ss -ltn | grep -q '172.17.0.1:9195 ' && break
  sleep 0.5
done
echo "uni-provider: $(systemctl is-active uni-provider), pubkey $(cat /var/lib/uni_provider_pubkey 2>/dev/null || echo '?')"
