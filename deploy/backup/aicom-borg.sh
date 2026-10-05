#!/usr/bin/env bash
# borg with this host's backup repository and secrets wired in (installed as
# /usr/local/sbin/aicom-borg):   aicom-borg list | aicom-borg info | aicom-borg extract ::ARCHIVE path
set -euo pipefail
EXTRA_ROOTS=()
# shellcheck source=/dev/null
. /etc/aicom-backup/backup.conf
export BORG_REPO="$REPO"
export BORG_PASSCOMMAND="cat /etc/aicom-backup/passphrase"
export BORG_RSH="ssh -i /etc/aicom-backup/id_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes -o UserKnownHostsFile=/etc/aicom-backup/known_hosts -o StrictHostKeyChecking=yes -o ServerAliveInterval=30"
export BORG_BASE_DIR=/var/lib/aicom-backup/borg
export BORG_RELOCATED_REPO_ACCESS_IS_OK=no BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=no
exec borg "$@"
