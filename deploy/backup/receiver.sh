#!/usr/bin/env bash
# Backup receiver: keeps other hosts' borg repositories without being able to read them.
#
#   receiver.sh setup                          borg, the aicom-backup user, weekly compact + check
#   receiver.sh add-client LABEL QUOTA < key   let one ssh public key reach
#                                              /srv/aicom-backups/LABEL and nothing else
#   receiver.sh status-page                    publish status.json for the alerter (every 10 min)
#
# Run as root on the receiver (PingBlip keeps everyone's backups; attested keeps PingBlip's).
#
# Clients encrypt on their side, so this host stores ciphertext. Each client key is pinned to
# a forced `borg serve --append-only --restrict-to-repository … --storage-quota …`: a client
# that is broken into can add archives, not delete or rewrite old ones, and cannot fill this
# disk past its quota. Its own prunes only mark archives deleted; the space comes back when
# THIS host runs `borg compact` (weekly; compact needs no key).
set -euo pipefail

ROOT=/srv/aicom-backups
ACCOUNT=aicom-backup
HERE="$(cd "$(dirname "$0")" && pwd)"

setup() {
  export DEBIAN_FRONTEND=noninteractive
  command -v borg >/dev/null || apt-get install -y -qq borgbackup >/dev/null
  if ! id "$ACCOUNT" >/dev/null 2>&1; then
    useradd --system --home-dir "$ROOT" --shell /bin/sh "$ACCOUNT"
  fi
  # '*' = no password, but not "locked": sshd refuses public keys for a '!' account
  # when PAM is off.
  usermod -p '*' "$ACCOUNT"
  install -d -m 0700 -o "$ACCOUNT" -g "$ACCOUNT" "$ROOT" "$ROOT/.ssh"
  touch "$ROOT/.ssh/authorized_keys"
  chown "$ACCOUNT:$ACCOUNT" "$ROOT/.ssh/authorized_keys"
  chmod 0600 "$ROOT/.ssh/authorized_keys"

  install -m 0755 "$HERE/receiver-maintain.sh" /usr/local/sbin/aicom-backup-maintain
  cat > /etc/systemd/system/aicom-backup-maintain.service <<UNIT
[Unit]
Description=Compact and check the borg repositories other hosts back up into
[Service]
Type=oneshot
User=$ACCOUNT
Environment=HOME=$ROOT BORG_BASE_DIR=$ROOT/.borg
ExecStart=/usr/local/sbin/aicom-backup-maintain
Nice=10
IOSchedulingClass=idle
UNIT
  cat > /etc/systemd/system/aicom-backup-maintain.timer <<UNIT
[Unit]
Description=Weekly compact + repository check of received backups
[Timer]
# Sunday midday UTC: clear of the nightly backup window.
OnCalendar=Sun *-*-* 12:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now aicom-backup-maintain.timer
  echo "receiver ready: $ROOT ($(df -h --output=avail "$ROOT" | tail -1 | tr -d ' ') free)"
}

add_client() {
  local label="$1" quota="$2" key
  [[ "$label" =~ ^[a-z0-9][a-z0-9-]{1,40}$ ]] || { echo "bad label: $label" >&2; exit 2; }
  [[ "$quota" =~ ^[0-9]+[GT]$ ]] || { echo "bad quota: $quota" >&2; exit 2; }
  read -r key
  [[ "$key" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+ ]] || { echo "not an ed25519 public key" >&2; exit 2; }
  key="$(awk '{print $1" "$2}' <<<"$key")"
  local line="command=\"borg serve --append-only --restrict-to-repository $ROOT/$label --storage-quota $quota\",restrict $key aicom-backup@$label"
  local keys="$ROOT/.ssh/authorized_keys"
  grep -v " aicom-backup@$label\$" "$keys" > "$keys.new" || true
  echo "$line" >> "$keys.new"
  chown "$ACCOUNT:$ACCOUNT" "$keys.new"; chmod 0600 "$keys.new"
  mv "$keys.new" "$keys"
  echo "client $label: append-only, quota $quota, repo $ROOT/$label"
}

status_page() {
  install -d -m 0755 /usr/local/lib/aicom-backup /var/www/aicom-backup-status
  install -m 0755 "$HERE/receiver_status.py" /usr/local/lib/aicom-backup/receiver_status.py
  cat > /etc/systemd/system/aicom-backup-status.service <<'UNIT'
[Unit]
Description=Publish backup freshness for the alerter
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/aicom-backup/receiver_status.py --root /srv/aicom-backups --out /var/www/aicom-backup-status/status.json --own-run /var/lib/aicom-backup/last-run.json
UNIT
  cat > /etc/systemd/system/aicom-backup-status.timer <<'UNIT'
[Unit]
Description=Publish backup freshness every 10 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now aicom-backup-status.timer
  systemctl start aicom-backup-status.service
  echo "status: /var/www/aicom-backup-status/status.json"
}

case "${1:-}" in
  setup) setup ;;
  add-client) add_client "${2:?label}" "${3:?quota, e.g. 30G}" ;;
  status-page) status_page ;;
  *) echo "usage: $0 setup | add-client LABEL QUOTA < pubkey | status-page" >&2; exit 2 ;;
esac
