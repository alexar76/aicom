#!/usr/bin/env bash
# indep321.sh prepare|smoke|roll|rollback — Independent's hub (systemd + venv) to 3.21.0, 2026-11-12.
#   prepare  copy the running venv and install the 3.21.0 wheel into the copy (no dependency changes)
#   smoke    pg_dump of the live DB into a temporary database on this server; the new venv opens and serves it,
#            then the running venv does (rollback proven); the temp DB is dropped. 3.21.0 has no migration.
#   roll     pg_dump backup, drop-in 99f-hub-3210-20261112.conf (sorts after every current drop-in), restart
#   rollback remove that drop-in, daemon-reload, restart (back to the 3.20.0 venv)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.20.0-20261111
NEWV=/opt/independentai/venvs/hub-3.21.0-20261112
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99f-hub-3210-20261112.conf
DB=independentai_hub
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  (cd "$K/wheels" && sha256sum -c SHA256SUMS)
  cp -a "$OLDV" "$NEWV"
  "$NEWV/bin/python" -m pip install -q --no-index --no-deps --force-reinstall "$K/wheels/aimarket_hub-3.21.0-py3-none-any.whl"
  "$NEWV/bin/python" -m pip check
  (cd /tmp && "$NEWV/bin/python" -c 'import aimarket_hub, importlib.metadata as m; print(aimarket_hub.__file__, aimarket_hub.__version__, "fastapi", m.version("fastapi"))')
  ;;
smoke)
  sudo -u postgres dropdb --if-exists hub321smoke
  sudo -u postgres createdb hub321smoke
  sudo -u postgres pg_dump -Fc "$DB" | sudo -u postgres pg_restore -d hub321smoke --no-owner --no-privileges
  install -m 644 "$K/smoke_db.py" /tmp/hub321-smoke_db.py   # run as postgres, which cannot read /root
  for mode in new old; do
    PY="$NEWV/bin/python"; [[ "$mode" == old ]] && PY="$OLDV/bin/python"
    SP="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/aimarket_hub/"
    (cd /tmp && sudo -u postgres env SMOKE_MODE=$mode SMOKE_EXPECT_PKG="$SP" \
      SMOKE_DATABASE_URL='postgresql://postgres@/hub321smoke?host=/var/run/postgresql' \
      "$PY" /tmp/hub321-smoke_db.py 2>&1 | tail -1)
  done
  sudo -u postgres dropdb hub321smoke; rm -f /tmp/hub321-smoke_db.py
  ;;
roll)
  T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /var/backups/independentai
  sudo -u postgres pg_dump -Fc "$DB" > "/var/backups/independentai/hub-pre-3210-$T.dump"
  chmod 600 "/var/backups/independentai/hub-pre-3210-$T.dump"; ls -la "/var/backups/independentai/hub-pre-3210-$T.dump"
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-12: hub 3.21.0 (release wheel e3dd66ef…; the AI Catalog door; same dependencies as 3.20.0).
# Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99e-hub-3200-20261111.conf).
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
