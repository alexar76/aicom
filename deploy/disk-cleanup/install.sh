#!/usr/bin/env bash
# install.sh — run on a host as root from a folder holding aicom_disk_cleanup.sh and the two units.
# Undo: systemctl disable --now aicom-disk-cleanup.timer; rm /etc/systemd/system/aicom-disk-cleanup.{service,timer}
#       /usr/local/sbin/aicom-disk-cleanup; systemctl daemon-reload
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
install -m 0755 "$D/aicom_disk_cleanup.sh" /usr/local/sbin/aicom-disk-cleanup
install -m 0644 "$D/aicom-disk-cleanup.service" "$D/aicom-disk-cleanup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aicom-disk-cleanup.timer
systemctl list-timers aicom-disk-cleanup.timer --no-pager | head -3
