#!/usr/bin/env bash
# indep320.sh prepare|smoke|roll|rollback — Independent's hub (systemd + venv) to 3.20.0, 2026-11-11.
#   prepare  copy the running venv, install the 3.20.0 wheel and the tested fastapi/starlette/cryptography
#   smoke    pg_dump of the live DB into a temporary database on this server; new venv migrates and serves it,
#            the running venv then starts on the migrated copy (rollback proven); the temp DB is dropped
#   roll     pg_dump backup, drop-in 99e-hub-3200-20261111.conf (sorts after every current drop-in), restart
#   rollback remove that drop-in, daemon-reload, restart (back to the 3.16.0 venv)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.16.0-rpc-security-20261031
NEWV=/opt/independentai/venvs/hub-3.20.0-20261111
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99e-hub-3200-20261111.conf
DB=independentai_hub
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  cp -a "$OLDV" "$NEWV"
  "$NEWV/bin/python" -m pip install -q --no-index --no-deps --force-reinstall "$K/wheels/aimarket_hub-3.20.0-py3-none-any.whl"
  "$NEWV/bin/python" -m pip install -q --no-cache-dir fastapi==0.162.4 starlette==1.10.0 cryptography==50.0.2
  "$NEWV/bin/python" -m pip check
  (cd /tmp && "$NEWV/bin/python" -c 'import aimarket_hub, importlib.metadata as m; print(aimarket_hub.__file__, aimarket_hub.__version__, "fastapi", m.version("fastapi"))')
  ;;
smoke)
  sudo -u postgres dropdb --if-exists hub320smoke
  sudo -u postgres createdb hub320smoke
  sudo -u postgres pg_dump -Fc "$DB" | sudo -u postgres pg_restore -d hub320smoke --no-owner --no-privileges
  install -m 644 "$K/smoke_db.py" /tmp/hub320-smoke_db.py   # run as postgres, which cannot read /root
  for mode in new old; do
    PY="$NEWV/bin/python"; [[ "$mode" == old ]] && PY="$OLDV/bin/python"
    SP="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/aimarket_hub/"
    (cd /tmp && sudo -u postgres env SMOKE_MODE=$mode SMOKE_EXPECT_PKG="$SP" \
      SMOKE_DATABASE_URL='postgresql://postgres@/hub320smoke?host=/var/run/postgresql' \
      "$PY" /tmp/hub320-smoke_db.py 2>&1 | tail -2)
  done
  sudo -u postgres dropdb hub320smoke; rm -f /tmp/hub320-smoke_db.py
  ;;
roll)
  T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /var/backups/independentai
  sudo -u postgres pg_dump -Fc "$DB" > "/var/backups/independentai/hub-pre-3200-$T.dump"
  chmod 600 "/var/backups/independentai/hub-pre-3200-$T.dump"; ls -la "/var/backups/independentai/hub-pre-3200-$T.dump"
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-11: hub 3.20.0 (release wheel e5001655…, fastapi 0.162.4, starlette 1.10.0, cryptography 50.0.2).
# Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99-security-20261031.conf).
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
