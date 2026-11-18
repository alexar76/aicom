#!/usr/bin/env bash
# Install the wholesale eSIM price recorder on the host that runs esim-node (factory-vps):
#   rsync -a scripts/esim-price-history/ factory-vps:/root/esim-price-history-install/
#   ssh factory-vps 'bash /root/esim-price-history-install/install.sh'
# Remove (keeps the recorded data in /var/lib/aicom/esim-price-history):
#   ssh factory-vps 'bash /root/esim-price-history-install/install.sh --remove'
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB=/usr/local/lib/aicom/esim-price-history
if [[ "${1:-}" == "--remove" ]]; then
  systemctl disable --now esim-price-history.timer 2>/dev/null || true
  rm -f /etc/systemd/system/esim-price-history.service /etc/systemd/system/esim-price-history.timer
  rm -rf "$LIB"
  systemctl daemon-reload
  echo "removed; data kept in /var/lib/aicom/esim-price-history"
  exit 0
fi
[[ -r /opt/esim-node-data/catalog-snapshot.json ]] || { echo "no esim-node snapshot on this host" >&2; exit 1; }
install -d -m 0755 "$LIB"
install -m 0755 "$HERE/esim_price_history.py" "$LIB/esim_price_history.py"
install -m 0644 "$HERE/esim-price-history.service" /etc/systemd/system/esim-price-history.service
install -m 0644 "$HERE/esim-price-history.timer" /etc/systemd/system/esim-price-history.timer
install -d -m 0750 /var/lib/aicom/esim-price-history
systemctl daemon-reload
systemctl start esim-price-history.service
systemctl enable --now esim-price-history.timer
systemctl list-timers --no-pager esim-price-history.timer
tail -n 2 /var/lib/aicom/esim-price-history/reads.jsonl
