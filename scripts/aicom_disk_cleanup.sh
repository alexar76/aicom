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
#     an image also stays when something on the host still needs it although nothing runs it right now: it carries
#     the label org.modelmarket.keep or org.modelmarket.histor.sandbox, /etc/aicom-disk-cleanup.keep lists it, or a
#     unit, cron table or program on the host names it (2026-11-02/03: the HISTOR package sandbox, which starts
#     histor-node:22 and :24 per run, lost them on pingblip and competing-lab and every npm observation failed);
#   - systemd journal beyond 200 MB, apt cache, pip / npm / go build caches of root.
# It never touches volumes, running or non-rollback containers, backups, databases or anything under /root
# except the caches named above. Log: /var/log/aicom-disk-cleanup.log.
set -uo pipefail
LOG=/var/log/aicom-disk-cleanup.log
STAMP=/var/lib/aicom-disk-cleanup/last-full-run
DISK_TRIGGER_PCT="${DISK_TRIGGER_PCT:-85}"
KEEP_DAYS="${KEEP_DAYS:-14}"
KEEP_FILE="${KEEP_FILE:-/etc/aicom-disk-cleanup.keep}"
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
# Keep the clock outside each pipeline and its background subprocesses. The unit has a final bound
# even when a Docker client is stuck in uninterruptible kernel I/O.
bounded_docker() { timeout --foreground --kill-after=10s 120s docker "$@"; }
run() {
  if [[ $DRY == 1 ]]; then log "DRY-RUN: $*"; return; fi
  log "RUN: $*"
  if [[ $1 == docker ]]; then
    bounded_docker "${@:2}" >>"$LOG" 2>&1 || log "  (exit $?)"
  else
    "$@" >>"$LOG" 2>&1 || log "  (exit $?)"
  fi
}
use_pct() { df --output=pcent / | tail -1 | tr -dc '0-9'; }
df_line() { df -h / | awk 'NR==2 {print $3 " used of " $2 ", " $4 " free (" $5 ")"}'; }

if [[ $IF_NEEDED == 1 ]]; then
  pct=$(use_pct); age=999999
  [[ -f $STAMP ]] && age=$(( $(date +%s) - $(stat -c %Y "$STAMP") ))
  if (( pct < DISK_TRIGGER_PCT && age < 72000 )); then exit 0; fi
  log "=== run: disk at ${pct} %, last full run $((age / 3600)) h ago ==="
fi
log "=== aicom disk cleanup on $(hostname) (dry_run=$DRY) — before: $(df_line) ==="

clean_docker() {
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
  done < <(bounded_docker ps -aq -f status=exited -f status=created | xargs -r timeout --foreground --kill-after=10s 120s docker inspect -f '{{.Id}} {{.Name}} {{.State.FinishedAt}} {{.Created}}' 2>/dev/null)

  # Images every container still uses (by id), and every image a compose file on this host names.
  # A stopped or slow daemon can return a partial inventory. Keep all tagged images in that case.
  if ! used=$(bounded_docker ps -aq | xargs -r timeout --foreground --kill-after=10s 120s docker inspect -f '{{.Image}}' 2>/dev/null | sort -u) ||
     ! images=$(bounded_docker images --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedAt}}'); then
    log '  Docker inventory incomplete; skipping tagged image cleanup'
    return
  fi
  named=$(find /opt /root /srv /home -maxdepth 4 \( -name 'docker-compose*.y*ml' -o -name 'compose*.y*ml' \) -type f 2>/dev/null \
            | xargs -r grep -h -E '^\s*image:' 2>/dev/null | sed -E 's/^\s*image:\s*//; s/["'\'']//g; s/\s+#.*$//' | sort -u)
  # Newest image id per repository, by creation time.
  newest=$(printf '%s\n' "$images" | sed -E 's/:[^: ]+( )/\1/' | grep -v '^<none>' \
             | sort -k1,1 -k3,4r | awk '!seen[$1]++ {print $2}' | sort -u)
  # Images the host lists as kept: /etc/aicom-disk-cleanup.keep, one shell glob per line matched against the
  # repository or the full reference (histor-node, histor-node:22, ghcr.io/org/*), # starts a comment.
  keep_globs=()
  if [[ -r $KEEP_FILE ]]; then
    while read -r g _; do [[ -z $g || $g == \#* ]] || keep_globs+=("$g"); done < "$KEEP_FILE"
  fi
  listed() { local g; for g in "${keep_globs[@]}"; do [[ $1 == $g || ${1%:*} == $g ]] && return 0; done; return 1; }
  kept() { [[ $DRY == 1 ]] && log "  keep $1: $2"; return 0; }

  cands=()
  while read -r ref id created; do
    [[ $ref == "<none>:<none>" ]] && continue
    # Base images stay: builds and the HISTOR sandbox pin them by tag (overlay-base, *-security-base, hubbase-*,
    # histor-python, histor-node) and the official ones would only be pulled again.
    [[ ${ref%:*} =~ (^|[/_-])base([_-]|$)|hubbase|histor-python|histor-node|(^|/)(python|node|nginx|alpine|debian|ubuntu|postgres|redis|busybox|golang|rust)$ ]] && continue
    grep -qx "$id" <<< "$used" && continue
    grep -qx "$id" <<< "$newest" && continue
    grep -qxF "$ref" <<< "$named" && continue
    grep -qxF "${ref%:latest}" <<< "$named" && continue
    t=$(date -d "${created% *}" +%s 2>/dev/null) || continue
    (( now - t > keep_s )) || continue
    listed "$ref" && { kept "$ref" "listed in $KEEP_FILE"; continue; }
    if ! labels=$(bounded_docker image inspect -f '{{json .Config.Labels}}' "$id" 2>/dev/null); then
      log "  keep $ref: Docker could not read image labels"
      continue
    fi
    [[ $labels =~ \"org\.modelmarket\.(keep|histor\.sandbox)\" ]] && { kept "$ref" "label"; continue; }
    cands+=("$ref")
  done <<< "$images"

  # References: a program that runs `docker run histor-node:22` needs that image although no container and no
  # compose file holds it. Search units, cron tables, /usr/local programs and the scripts and configs under
  # /opt, /srv, /root and /home (not git trees, virtualenvs, node_modules or backups) for each candidate's
  # reference, and for its repository alone when the tag is latest. Only the matched references are printed.
  referenced=""
  if (( ${#cands[@]} )); then
    pats=$(for r in "${cands[@]}"; do echo "$r"; [[ $r == *:latest ]] && echo "${r%:latest}"; done)
    referenced=$(
      { find /etc/systemd/system /etc/cron.d /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly \
             /var/spool/cron /usr/local/bin /usr/local/sbin -maxdepth 3 -type f -size -2M 2>/dev/null
        find /etc -maxdepth 1 -type f \( -name crontab -o -name '*.env' \) 2>/dev/null
        find /opt /srv /root /home -maxdepth 5 \
             \( -name .git -o -name node_modules -o -name 'venv*' -o -name .venv -o -name site-packages \
                -o -name __pycache__ -o -name 'aicom-backups' -o -name backups \) -prune -o \
             -type f -size -1M \( -name '*.sh' -o -name '*.py' -o -name '*.env' -o -name '.env' -o -name '*.service' \
                -o -name '*.timer' -o -name '*.conf' -o -name '*.json' -o -name '*.toml' -o -name '*.ini' \
                -o -name '*.y*ml' -o -name Makefile -o -name '*.mjs' -o -name '*.js' \) -print 2>/dev/null
      } | tr '\n' '\0' | xargs -0 -r grep -hoswF -f <(printf '%s\n' "$pats") 2>/dev/null | sort -u)
  fi
  for ref in "${cands[@]}"; do
    if grep -qxF "$ref" <<< "$referenced" || { [[ $ref == *:latest ]] && grep -qxF "${ref%:latest}" <<< "$referenced"; }; then
      kept "$ref" "named by a program or unit on this host"; continue
    fi
    run docker rmi "$ref"
  done
  run docker image prune -f
}

if command -v docker >/dev/null 2>&1 && bounded_docker info >/dev/null 2>&1; then
  clean_docker
fi

command -v journalctl >/dev/null && run journalctl --vacuum-size=200M
command -v apt-get >/dev/null && run apt-get clean
for d in /root/.cache/pip /root/.cache/go-build /root/.npm/_cacache; do
  [[ -d $d ]] && run rm -rf "$d"
done

[[ $DRY == 0 ]] && touch "$STAMP"
log "=== done — after: $(df_line) ==="
