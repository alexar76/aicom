#!/usr/bin/env bash
# aicom_disk_cleanup.sh — one safe disk cleanup for every aicom host (not my-vps).
#
#   aicom_disk_cleanup.sh [--dry-run] [--if-needed]
#
# --if-needed runs only when / is at or above DISK_TRIGGER_PCT (85, the alerter's threshold) or the last full run
# is more than 20 h old; the hourly aicom-disk-cleanup.timer calls it that way, so a filling disk gets a cleanup
# within the hour instead of a page and nothing else (owner, 2026-11-02).
#
# What it removes, and only this:
#   - Docker build cache older than 72 h, and dangling images;
#   - stopped ROLLBACK containers that finished more than 14 days ago: names with -prev, -security-prev-, -before
#     or -rollback (rollout_container.py, roll.sh and the hand deploys name them so);
#   - tagged images older than 14 days that no container uses (running or stopped), that are not the newest image
#     of their repository, that are not a base image (local or official), and that no compose file on the host names. The newest-per-repository rule keeps the
#     last good image of a service that is down at the moment (2026-10: a stopped Alien Monitor lost its only image
#     to `docker system prune -a` and served 502); `docker rmi` without -f refuses anything still in use;
#   - systemd journal beyond 200 MB, apt cache, pip / npm / go build caches of root.
# It never touches volumes, running or non-rollback containers, backups, databases or anything under /root
# except the caches named above. Log: /var/log/aicom-disk-cleanup.log.
set -uo pipefail
LOG=/var/log/aicom-disk-cleanup.log
STAMP=/var/lib/aicom-disk-cleanup/last-full-run
DISK_TRIGGER_PCT="${DISK_TRIGGER_PCT:-85}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DRY=0; IF_NEEDED=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --if-needed) IF_NEEDED=1 ;;
    *) echo "unknown argument $a" >&2; exit 2 ;;
  esac
done
exec 9>/run/aicom-disk-cleanup.lock
flock -n 9 || { echo "another cleanup is running"; exit 0; }
mkdir -p "$(dirname "$STAMP")"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
run() { if [[ $DRY == 1 ]]; then log "DRY-RUN: $*"; else log "RUN: $*"; "$@" >>"$LOG" 2>&1 || log "  (exit $?)"; fi; }
use_pct() { df --output=pcent / | tail -1 | tr -dc '0-9'; }
df_line() { df -h / | awk 'NR==2 {print $3 " used of " $2 ", " $4 " free (" $5 ")"}'; }

if [[ $IF_NEEDED == 1 ]]; then
  pct=$(use_pct); age=999999
  [[ -f $STAMP ]] && age=$(( $(date +%s) - $(stat -c %Y "$STAMP") ))
  if (( pct < DISK_TRIGGER_PCT && age < 72000 )); then exit 0; fi
  log "=== run: disk at ${pct} %, last full run $((age / 3600)) h ago ==="
fi
log "=== aicom disk cleanup on $(hostname) (dry_run=$DRY) — before: $(df_line) ==="

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  run docker builder prune -f --filter until=72h
  run docker image prune -f

  now=$(date +%s); keep_s=$(( KEEP_DAYS * 86400 ))
  # Stopped rollback containers past the keep window.
  while read -r id name fin created; do
    [[ $name =~ (-prev|-security-prev-|-before|-rollback) ]] || continue
    # A container that never ran (status "created", as rollout_container.py leaves its rollback copies) has
    # FinishedAt 0001-01-01: age it by creation, or it reads as two thousand years old (2026-11-02, admin-vps).
    [[ $fin == 0001-* ]] && fin=$created
    t=$(date -d "$fin" +%s 2>/dev/null) || continue
    (( now - t > keep_s )) || continue
    log "  rollback container ${name#/}, finished $fin"
    run docker rm "$id"
  done < <(docker ps -aq -f status=exited -f status=created | xargs -r docker inspect -f '{{.Id}} {{.Name}} {{.State.FinishedAt}} {{.Created}}' 2>/dev/null)

  # Images every container still uses (by id), and every image a compose file on this host names.
  used=$(docker ps -aq | xargs -r docker inspect -f '{{.Image}}' 2>/dev/null | sort -u)
  named=$(find /opt /root /srv /home -maxdepth 4 \( -name 'docker-compose*.y*ml' -o -name 'compose*.y*ml' \) -type f 2>/dev/null \
            | xargs -r grep -h -E '^\s*image:' 2>/dev/null | sed -E 's/^\s*image:\s*//; s/["'\'']//g; s/\s+#.*$//' | sort -u)
  # Newest image id per repository, by creation time.
  newest=$(docker images --no-trunc --format '{{.Repository}} {{.ID}} {{.CreatedAt}}' | grep -v '^<none>' \
             | sort -k1,1 -k3,4r | awk '!seen[$1]++ {print $2}' | sort -u)
  while read -r ref id created; do
    [[ $ref == "<none>:<none>" ]] && continue
    # Base images stay: builds and the HISTOR sandbox pin them by tag (overlay-base, *-security-base, hubbase-*,
    # histor-python) and the official ones would only be pulled again.
    [[ ${ref%:*} =~ (^|[/_-])base([_-]|$)|hubbase|histor-python|(^|/)(python|node|nginx|alpine|debian|ubuntu|postgres|redis|busybox|golang|rust)$ ]] && continue
    grep -qx "$id" <<< "$used" && continue
    grep -qx "$id" <<< "$newest" && continue
    grep -qxF "$ref" <<< "$named" && continue
    grep -qxF "${ref%:latest}" <<< "$named" && continue
    t=$(date -d "${created% *}" +%s 2>/dev/null) || continue
    (( now - t > keep_s )) || continue
    run docker rmi "$ref"
  done < <(docker images --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}')
  run docker image prune -f
fi

command -v journalctl >/dev/null && run journalctl --vacuum-size=200M
command -v apt-get >/dev/null && run apt-get clean
for d in /root/.cache/pip /root/.cache/go-build /root/.npm/_cacache; do
  [[ -d $d ]] && run rm -rf "$d"
done

[[ $DRY == 0 ]] && touch "$STAMP"
log "=== done — after: $(df_line) ==="
