#!/usr/bin/env bash
# install.sh — run on a host as root from a folder holding aicom_disk_cleanup.sh, the two units and
# aicom-disk-cleanup.keep.
# Undo: systemctl disable --now aicom-disk-cleanup.timer; rm /etc/systemd/system/aicom-disk-cleanup.{service,timer}
#       /usr/local/sbin/aicom-disk-cleanup /etc/aicom-disk-cleanup.keep; systemctl daemon-reload
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
install -m 0755 "$D/aicom_disk_cleanup.sh" /usr/local/sbin/aicom-disk-cleanup
install -m 0644 "$D/aicom-disk-cleanup.service" "$D/aicom-disk-cleanup.timer" /etc/systemd/system/
# The keep list: a new host gets the shipped file; an existing one gets the shipped lines it lacks, and the
# lines the host added stay.
if [[ ! -e /etc/aicom-disk-cleanup.keep ]]; then
  install -m 0644 "$D/aicom-disk-cleanup.keep" /etc/aicom-disk-cleanup.keep
else
  while read -r g _; do
    [[ -z $g || $g == \#* ]] && continue
    grep -qxF "$g" /etc/aicom-disk-cleanup.keep || echo "$g" >> /etc/aicom-disk-cleanup.keep
  done < "$D/aicom-disk-cleanup.keep"
fi
systemctl daemon-reload
systemctl enable --now aicom-disk-cleanup.timer
systemctl list-timers aicom-disk-cleanup.timer --no-pager | head -3
