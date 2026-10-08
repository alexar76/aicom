#!/usr/bin/env bash
# Put one host on the nightly off-host backup and register it with its receiver.
# Run from the owner's Mac: besides the host itself, that is the only place allowed to hold
# the host's passphrase.
#
#   deploy/backup/install.sh HOST LABEL RECEIVER RECEIVER_ADDR QUOTA [EXTRA_ROOT...]
#   deploy/backup/install.sh factory-vps factory-vps root@RECEIVER RECEIVER_ADDR 30G /var/lib/aicom
#
# HOST and RECEIVER are ssh destinations from this machine. RECEIVER_ADDR is how HOST reaches
# the receiver: ADDR or ADDR:PORT (admin-vps's provider blocks outgoing 22, so it uses the
# receiver's port 2222, open to its address only). LABEL names the repository
# (/srv/aicom-backups/LABEL on the receiver). Idempotent: re-running updates the scripts and
# keeps the key, the passphrase and the repository.
#
# Secrets are made ON the host (/etc/aicom-backup/passphrase, id_ed25519) and copied to
# ~/.aicom-backup/LABEL/ here — passphrase and exported repo key, 0600, never printed.
# Without them the archives cannot be opened: keep an offline copy of ~/.aicom-backup.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
host="${1:?host}" label="${2:?label}" recv="${3:?receiver}" recv_addr="${4:?receiver address}" quota="${5:?quota}"
shift 5
extra=("$@")
[[ "$label" =~ ^[a-z0-9][a-z0-9-]{1,40}$ ]] || { echo "bad label" >&2; exit 2; }
recv_ip="${recv_addr%%:*}"
recv_port="${recv_addr#"$recv_ip"}"; recv_port="${recv_port#:}"
known_name="$recv_ip"; [[ -n "$recv_port" ]] && known_name="[$recv_ip]:$recv_port"
KEY="${AICOM_SSH_KEY:-$HOME/.ssh/id_ed25519_factory}"
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15)
VAULT="$HOME/.aicom-backup/$label"

echo "== receiver $recv: borg, account, weekly compact"
COPYFILE_DISABLE=1 tar --no-xattrs -C "$HERE" -cf - receiver.sh receiver-maintain.sh receiver_status.py \
  | "${SSH[@]}" "$recv" 'install -d -m 0755 /usr/local/lib/aicom-backup-receiver && tar -C /usr/local/lib/aicom-backup-receiver -xf - && /usr/local/lib/aicom-backup-receiver/receiver.sh setup'

echo "== $host: borg, scripts, units"
COPYFILE_DISABLE=1 tar --no-xattrs -C "$HERE" -cf - aicom-backup.sh aicom-borg.sh sqlite_snapshot.py excludes aicom-backup.service aicom-backup.timer README.md \
  | "${SSH[@]}" "$host" 'install -d -m 0755 /usr/local/lib/aicom-backup && tar -C /usr/local/lib/aicom-backup -xf -'
"${SSH[@]}" "$host" bash -s -- "$label" "$recv_addr" ${extra[@]+"${extra[@]}"} <<'REMOTE'
set -euo pipefail
label="$1" recv_addr="$2"; shift 2
export DEBIAN_FRONTEND=noninteractive
command -v borg >/dev/null || apt-get install -y -qq borgbackup >/dev/null
L=/usr/local/lib/aicom-backup
install -m 0755 "$L/aicom-backup.sh" /usr/local/sbin/aicom-backup
install -m 0755 "$L/aicom-borg.sh" /usr/local/sbin/aicom-borg
install -d -m 0700 /etc/aicom-backup /var/lib/aicom-backup
install -m 0644 "$L/excludes" /etc/aicom-backup/excludes
{
  echo "# written by deploy/backup/install.sh"
  echo "LABEL=$label"
  echo "REPO=ssh://aicom-backup@$recv_addr/srv/aicom-backups/$label"
  printf 'EXTRA_ROOTS=('; (( $# )) && printf '%q ' "$@"; echo ')'
} > /etc/aicom-backup/backup.conf
chmod 0600 /etc/aicom-backup/backup.conf
umask 077
[[ -f /etc/aicom-backup/id_ed25519 ]] \
  || ssh-keygen -q -t ed25519 -N '' -C "aicom-backup@$label" -f /etc/aicom-backup/id_ed25519
[[ -s /etc/aicom-backup/passphrase ]] \
  || head -c 48 /dev/urandom | base64 -w0 > /etc/aicom-backup/passphrase
install -m 0644 "$L/aicom-backup.service" "$L/aicom-backup.timer" /etc/systemd/system/
systemctl daemon-reload
REMOTE

echo "== pin the receiver's host key on $host"
recv_key="$("${SSH[@]}" "$recv" 'cat /etc/ssh/ssh_host_ed25519_key.pub' | awk '{print $1" "$2}')"
[[ "$recv_key" =~ ^ssh-ed25519\  ]] || { echo "no ed25519 host key on the receiver" >&2; exit 1; }
"${SSH[@]}" "$host" "umask 077; echo '$known_name $recv_key' > /etc/aicom-backup/known_hosts"

echo "== allow $label on the receiver (append-only, quota $quota)"
"${SSH[@]}" "$host" 'cat /etc/aicom-backup/id_ed25519.pub' \
  | "${SSH[@]}" "$recv" "/usr/local/lib/aicom-backup-receiver/receiver.sh add-client $label $quota"

echo "== repository"
"${SSH[@]}" "$host" 'aicom-borg info >/dev/null 2>&1 && echo "exists" || aicom-borg init --encryption=repokey-blake2'

echo "== secrets to $VAULT (not printed)"
( umask 077; mkdir -p "$VAULT"
  "${SSH[@]}" "$host" 'cat /etc/aicom-backup/passphrase' > "$VAULT/passphrase.tmp"
  "${SSH[@]}" "$host" 'aicom-borg key export' > "$VAULT/repokey.tmp"
  [[ -s "$VAULT/passphrase.tmp" && -s "$VAULT/repokey.tmp" ]] || { echo "secret copy failed" >&2; exit 1; }
  mv "$VAULT/passphrase.tmp" "$VAULT/passphrase"; mv "$VAULT/repokey.tmp" "$VAULT/repokey"
  printf 'host=%s\nrepo=ssh://aicom-backup@%s/srv/aicom-backups/%s\n' "$host" "$recv_addr" "$label" > "$VAULT/where" )
echo "   passphrase $(wc -c < "$VAULT/passphrase" | tr -d ' ') bytes, repokey $(wc -l < "$VAULT/repokey" | tr -d ' ') lines"

"${SSH[@]}" "$host" 'systemctl enable --now aicom-backup.timer >/dev/null && systemctl list-timers aicom-backup.timer --no-pager | sed -n 2p'
echo "installed: $label -> $recv_addr. First run now:  ssh $host systemctl start --no-block aicom-backup"
