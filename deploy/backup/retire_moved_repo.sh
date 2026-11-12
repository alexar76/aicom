#!/usr/bin/env bash
# Retire the old copy of a backup repository that moved to another receiver, once the new receiver
# shows that the client has written to it there.
#
#   retire_moved_repo.sh LABEL NEW_STATUS_URL MOVED_AT [--dry-run]
#
# Run as root on the OLD receiver (a timer runs it hourly until it is done; see the install lines at
# the end of artifacts/admin-vps-backup-move-2026-11-10/README.md). It deletes /srv/aicom-backups/LABEL
# and LABEL's key line in the receiver's authorized_keys only when the new receiver's status page:
#   - was published within the last hour,
#   - shows a commit of LABEL after MOVED_AT (the client wrote there after the move), and
#   - shows LABEL at no less than 95 % of the old copy's size (nothing was lost on the way).
# Otherwise it keeps everything and says why. Each run is a line in /var/log/aicom-backup-retire-LABEL.log.
# When it is done, it disables its own timer (aicom-backup-retire-LABEL.timer).
set -uo pipefail
LABEL="${1:?label}" URL="${2:?new receiver status url}" MOVED_AT="${3:?moved-at UTC, e.g. 2026-11-10T06:00:00Z}"
DRY="${4:-}"
ROOT=/srv/aicom-backups
OLD="$ROOT/$LABEL"
LOG="/var/log/aicom-backup-retire-$LABEL.log"
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

[[ "$LABEL" =~ ^[a-z0-9][a-z0-9-]{1,40}$ ]] || { echo "bad label: $LABEL" >&2; exit 2; }
if [[ ! -d "$OLD" ]]; then
  say "$OLD is already gone; nothing to do"
  [[ -z "$DRY" ]] && systemctl disable --now "aicom-backup-retire-$LABEL.timer" 2> /dev/null
  exit 0
fi
old_mb="$(du -sm "$OLD" | cut -f1)"
status="$(curl -fsS --max-time 30 "$URL" 2>&1)" || { say "keep: $URL unreadable (${status:0:120})"; exit 0; }
verdict="$(python3 -c '
import json, sys, time, calendar
doc, label, moved, old_mb = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], float(sys.argv[4])
def ts(s):
    try: return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception: return None
gen = ts(str(doc.get("generated_at", "")))
if gen is None or time.time() - gen > 3600:
    print("keep: the new status page is stale or unreadable"); sys.exit()
row = (doc.get("repos") or {}).get(label)
if not row:
    print("keep: the new receiver does not list " + label); sys.exit()
last, size = ts(str(row.get("last_commit") or "")), row.get("size_mb")
if last is None or last <= ts(moved):
    print("keep: last commit there is %s, not after the move (%s)" % (row.get("last_commit"), moved)); sys.exit()
if not isinstance(size, (int, float)) or size < 0.95 * old_mb:
    print("keep: %s MB there against %.0f MB here" % (size, old_mb)); sys.exit()
print("retire: committed there at %s, %.0f MB there against %.0f MB here" % (row["last_commit"], size, old_mb))
' "$status" "$LABEL" "$MOVED_AT" "$old_mb" 2>&1)"
say "$verdict"
[[ "$verdict" == retire:* ]] || exit 0
if [[ -n "$DRY" ]]; then
  say "dry run: would delete $OLD and the key line aicom-backup@$LABEL"
  exit 0
fi
keys="$ROOT/.ssh/authorized_keys"
grep -v " aicom-backup@$LABEL\$" "$keys" > "$keys.new" || true
chown aicom-backup:aicom-backup "$keys.new"; chmod 0600 "$keys.new"; mv "$keys.new" "$keys"
rm -rf "$OLD"
say "deleted $OLD (${old_mb} MB) and the key line of $LABEL; free now $(df -h --output=avail / | tail -1 | tr -d ' ')"
systemctl disable --now "aicom-backup-retire-$LABEL.timer" 2> /dev/null
exit 0
