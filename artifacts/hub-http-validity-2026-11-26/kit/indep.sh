#!/usr/bin/env bash
# indep.sh prepare|smoke|roll|rollback — Independent's hub (systemd + venv): the HTTP validity change over the
# running fedvalid venv, 2026-11-26.
#   prepare  copy the running venv, put in the changed files (refuses unless the running ones are the expected ones)
#   smoke    pg_dump of the live DB into a temporary database; the new venv migrates (073) and serves it with the
#            headers and 304; then the running venv does (rollback proven); the temporary DB is dropped
#   roll     pg_dump backup, drop-in 99j (sorts after 99i), restart, wait for health
#   rollback remove that drop-in, daemon-reload, restart (back to the fedvalid venv via 99i)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.22.0-fedvalid-20261126
NEWV=/opt/independentai/venvs/hub-3.22.0-httpvalid-20261126
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99j-hub-httpvalid-20261126.conf
DB=independentai_hub
pkg() { echo "$("$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/aimarket_hub"; }
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  P="$(pkg "$OLDV")"
  have="$(for f in config.py crawler.py database.py realm.py hub_routes/wellknown.py migrations.py models.py hub_routes/catalog.py; do echo "$f $(sha256sum "$P/$f" | cut -c1-12)"; done)"
  want="config.py 747104c4b6d1
crawler.py f584cea89b63
database.py e9cfd5e7026b
realm.py c5c13552b507
hub_routes/wellknown.py cbff1787ba8c
migrations.py 12df83981701
models.py 3b2024764fd9
hub_routes/catalog.py 8d3ee72e1c0a"
  [[ "$have" == "$want" ]] || { echo "unexpected running files:"; diff <(echo "$want") <(echo "$have"); exit 3; }
  cp -a "$OLDV" "$NEWV"
  N="$(pkg "$NEWV")"
  install -m 644 "$K"/files/{crawler,database,migrations,models,http_validity}.py "$N/"
  install -m 644 "$K/files/hub_routes/wellknown.py" "$N/hub_routes/wellknown.py"
  install -m 644 "$K/catalog/catalog-3220.py" "$N/hub_routes/catalog.py"
  find "$N" -name '__pycache__' -prune -exec rm -rf {} +
  ;;
smoke)
  sudo -u postgres dropdb --if-exists hubvalidsmoke
  sudo -u postgres createdb hubvalidsmoke
  sudo -u postgres pg_dump -Fc "$DB" | sudo -u postgres pg_restore -d hubvalidsmoke --no-owner --no-privileges
  install -m 644 "$K/smoke_db.py" /tmp/hubvalid-smoke_db.py
  for mode in new old; do
    PY="$NEWV/bin/python"; [[ "$mode" == old ]] && PY="$OLDV/bin/python"
    (cd /tmp && sudo -u postgres env SMOKE_MODE=$mode SMOKE_EXPECT_PKG="$(pkg "${PY%/bin/python}")/" \
      SMOKE_DATABASE_URL='postgresql://postgres@/hubvalidsmoke?host=/var/run/postgresql' \
      "$PY" /tmp/hubvalid-smoke_db.py 2>&1 | tail -1)
  done
  sudo -u postgres dropdb hubvalidsmoke; rm -f /tmp/hubvalid-smoke_db.py
  ;;
roll)
  T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /var/backups/independentai
  sudo -u postgres pg_dump -Fc "$DB" > "/var/backups/independentai/hub-pre-httpvalid-$T.dump"
  chmod 600 "/var/backups/independentai/hub-pre-httpvalid-$T.dump"; ls -la "/var/backups/independentai/hub-pre-httpvalid-$T.dump"
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-26: HTTP validity (Cache-Control max-age + stale-if-error, weak ETag, 304; peer-stated period;
# migration 073) over the fedvalid venv. Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99i).
ExecStart=
ExecStart=$NEWV/bin/python -m aimarket_hub serve
EOD
  systemctl daemon-reload; systemctl restart "$UNIT"
  for i in $(seq 1 60); do curl -fsS -o /dev/null http://127.0.0.1:9083/ai-market/v2/health 2>/dev/null && break; sleep 1; done
  systemctl is-active "$UNIT"; tr '\0' ' ' < "/proc/$(systemctl show -p MainPID --value "$UNIT")/cmdline"; echo
  ;;
rollback)
  rm -f "$DROPIN"; systemctl daemon-reload; systemctl restart "$UNIT"; systemctl is-active "$UNIT"
  ;;
*) echo "usage: $0 prepare|smoke|roll|rollback" >&2; exit 2 ;;
esac
