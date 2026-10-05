#!/usr/bin/env bash
# Nightly off-host backup of this machine (installed as /usr/local/sbin/aicom-backup).
#
# 1. Every running Postgres container is dumped with pg_dumpall (and a host Postgres, if one
#    runs); their raw data directories stay out of the archive — a live data dir copied file
#    by file is not a database.
# 2. Every SQLite file under the roots is copied through the backup API (sqlite_snapshot.py),
#    the live file stays out.
# 3. borg sends it all to the receiver, encrypted HERE: the passphrase lives in
#    /etc/aicom-backup/passphrase and on the owner's Mac, never on the receiver. The receiver
#    lets this host append only, so a break-in here cannot erase what was already sent.
# 4. Old archives are pruned (14 daily, 8 weekly, 6 monthly); the receiver frees the space.
#
# Result: /var/lib/aicom-backup/last-run.json. Settings: /etc/aicom-backup/backup.conf.
# Restore: deploy/backup/README.md.
set -uo pipefail

CONF=/etc/aicom-backup/backup.conf
STATE_DIR=/var/lib/aicom-backup
STAGE=/var/tmp/aicom-backup
LIB=/usr/local/lib/aicom-backup
MIN_FREE_GB=${AICOM_BACKUP_MIN_FREE_GB:-5}

EXTRA_ROOTS=()
# shellcheck source=/dev/null
. "$CONF"
: "${LABEL:?}" "${REPO:?}"
ROOTS=(/etc /root /home /opt /srv /usr/local /var/www /var/spool/cron /var/lib/docker/volumes
       "${EXTRA_ROOTS[@]}")
existing=()
for r in "${ROOTS[@]}"; do [[ -e "$r" ]] && existing+=("$r"); done
ROOTS=("${existing[@]}")

borg() { /usr/local/sbin/aicom-borg "$@"; }  # repository, passphrase and ssh key wired in

exec 9>/run/aicom-backup.lock
flock -n 9 || { echo "another backup is running" >&2; exit 0; }

started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
errors=()
warnings=()
pg_count=0
sqlite_json='{}'
mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
rm -rf "$STAGE" && install -d -m 700 "$STAGE" "$STAGE/pg" "$STAGE/sqlite"
exclude_list="$STAGE/exclude.generated"
: > "$exclude_list"

finish() {
  local ok=$1 archive=${2:-} stats=${3:-}
  python3 - "$STATE_DIR/last-run.json" "$LABEL" "$started" "$ok" "$archive" "$stats" \
    "$pg_count" "$sqlite_json" "$(printf '%s\n' "${errors[@]}")" \
    "$(printf '%s\n' "${warnings[@]}")" <<'PY'
import json, os, sys, time
out, label, started, ok, archive, stats, pg, sq, errs, warns = sys.argv[1:11]
try:
    stats = json.loads(stats) if stats else {}
except ValueError:
    stats = {}
arch = stats.get("archive") or {}
try:
    sq = json.loads(sq)
except ValueError:
    sq = {}
doc = {
    "label": label, "started_at": started,
    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "ok": ok == "1", "archive": archive or None,
    "pg_dumps": int(pg), "sqlite_snapshots": sq.get("snapshots", 0),
    "sqlite_failed": sq.get("failed", []),
    "original_mb": round((arch.get("stats") or {}).get("original_size", 0) / 1e6, 1),
    "deduplicated_mb": round((arch.get("stats") or {}).get("deduplicated_size", 0) / 1e6, 1),
    "errors": [e for e in errs.splitlines() if e],
    "warnings": [w for w in warns.splitlines() if w][:20],
}
tmp = out + ".tmp"
with open(tmp, "w") as fh:
    json.dump(doc, fh, indent=1)
os.replace(tmp, out)
PY
  rm -rf "$STAGE"
  [[ "$ok" == 1 ]] && exit 0 || exit 1
}

free_gb="$(df --output=avail -BG /var/tmp | tail -1 | tr -dc '0-9')"
if (( free_gb < MIN_FREE_GB )); then
  errors+=("only ${free_gb} GB free on /var/tmp, need ${MIN_FREE_GB}")
  finish 0
fi

# ── 1. Postgres ──────────────────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  while read -r name image; do
    [[ "$image" =~ postgres|postgis|pgvector|timescale ]] || continue
    # A container from a postgres image with no server up (a throwaway restore, a one-off
    # psql) is not a database to dump; its files stay in the archive as they are.
    if ! docker exec "$name" pg_isready -q >/dev/null 2>&1; then
      warnings+=("postgres in $name is not accepting connections: not dumped, files kept raw")
      continue
    fi
    if docker exec "$name" sh -c 'PGPASSWORD="${POSTGRES_PASSWORD:-}" exec pg_dumpall -U "${POSTGRES_USER:-postgres}" --clean --if-exists' \
         > "$STAGE/pg/$name.sql" 2> "$STAGE/pg/$name.err"; then
      pg_count=$((pg_count + 1))
      rm -f "$STAGE/pg/$name.err"
      # the data directory itself stays out: the dump is the backup
      src="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}' "$name")"
      [[ -n "$src" ]] && echo "pp:${src%/_data}" >> "$exclude_list"
    else
      errors+=("pg_dumpall in $name failed: $(head -c 200 "$STAGE/pg/$name.err" | tr '\n' ' ')")
    fi
  done < <(docker ps --format '{{.Names}} {{.Image}}')
fi
if systemctl is-active --quiet postgresql 2>/dev/null; then
  if (cd / && runuser -u postgres -- pg_dumpall --clean --if-exists) > "$STAGE/pg/host-postgresql.sql" 2> "$STAGE/pg/host.err"; then
    pg_count=$((pg_count + 1)); rm -f "$STAGE/pg/host.err"
    echo "pp:/var/lib/postgresql" >> "$exclude_list"
  else
    errors+=("host pg_dumpall failed: $(head -c 200 "$STAGE/pg/host.err" | tr '\n' ' ')")
  fi
fi

# ── 2. SQLite ────────────────────────────────────────────────────────────────────────────
pattern_files=(--exclude-from /etc/aicom-backup/excludes --exclude-from "$exclude_list")
[[ -f /etc/aicom-backup/excludes.local ]] && pattern_files+=(--exclude-from /etc/aicom-backup/excludes.local)
sqlite_json="$(python3 "$LIB/sqlite_snapshot.py" --stage "$STAGE/sqlite" --exclude-out "$exclude_list.sqlite" \
                 "${pattern_files[@]}" "${ROOTS[@]}" 2> "$STAGE/sqlite.err")" \
  || errors+=("sqlite snapshots crashed: $(tail -c 300 "$STAGE/sqlite.err" | tr '\n' ' ')")
[[ -f "$exclude_list.sqlite" ]] && cat "$exclude_list.sqlite" >> "$exclude_list"
[[ -n "$sqlite_json" ]] || sqlite_json='{}'
while read -r line; do [[ -n "$line" ]] && warnings+=("sqlite kept raw: $line"); done \
  < <(python3 -c 'import json,sys; [print(p, "-", e) for p, e in json.loads(sys.argv[1]).get("failed", [])]' "$sqlite_json" 2>/dev/null)

# ── 3. borg create ───────────────────────────────────────────────────────────────────────
archive="files-$(date -u +%Y-%m-%dT%H%M%SZ)"
borg_excludes=(--exclude-from /etc/aicom-backup/excludes --exclude-from "$exclude_list")
[[ -f /etc/aicom-backup/excludes.local ]] && borg_excludes+=(--exclude-from /etc/aicom-backup/excludes.local)
stats="$(borg create --json --lock-wait 600 --compression zstd,6 --exclude-caches \
           "${borg_excludes[@]}" "::$archive" "${ROOTS[@]}" "$STAGE" 2> "$STATE_DIR/borg-create.log")"
rc=$?
# rc 1 = finished with warnings (a file changed or vanished while being read)
if (( rc > 1 )); then
  errors+=("borg create rc=$rc: $(grep -v '^$' "$STATE_DIR/borg-create.log" | tail -n 3 | tr '\n' ' ' | head -c 400)")
  finish 0 "" ""
fi
(( rc == 1 )) && warnings+=("borg create: $(grep -c . "$STATE_DIR/borg-create.log") warning line(s), see $STATE_DIR/borg-create.log")

# ── 4. prune (the receiver compacts) ─────────────────────────────────────────────────────
if ! borg prune --lock-wait 600 --glob-archives 'files-*' \
       --keep-daily 14 --keep-weekly 8 --keep-monthly 6 2> "$STATE_DIR/borg-prune.log"; then
  warnings+=("borg prune failed: $(tail -n 2 "$STATE_DIR/borg-prune.log" | tr '\n' ' ')")
fi
# Once a month, read the newest archive back end to end.
if [[ "$(date -u +%d)" == "01" ]]; then
  borg check --lock-wait 600 --archives-only --last 1 2> "$STATE_DIR/borg-check.log" \
    || errors+=("borg check of the newest archive failed: $(tail -n 2 "$STATE_DIR/borg-check.log" | tr '\n' ' ')")
fi

(( ${#errors[@]} == 0 )) && finish 1 "$archive" "$stats" || finish 0 "$archive" "$stats"
