#!/usr/bin/env bash
# indep.sh prepare|check|roll|rollback — Independent's hub (systemd + venv): the four files of the federated
# validity bound over the running 3.22.0 venv, 2026-11-26.
#   prepare  copy the running venv, replace the four files (refuses unless the running ones are the expected ones)
#   check    the new venv imports and, read-only against the live database, reports what the bound serves/hides
#   roll     pg_dump backup, drop-in 99i (sorts after 99h), restart, wait for health
#   rollback remove that drop-in, daemon-reload, restart (back to the 3.22.0 venv via 99h)
set -euo pipefail
OLDV=/opt/independentai/venvs/hub-3.22.0-20261121
NEWV=/opt/independentai/venvs/hub-3.22.0-fedvalid-20261126
K="$(cd "$(dirname "$0")" && pwd)"
UNIT=independentai-hub.service
DROPIN=/etc/systemd/system/$UNIT.d/99i-hub-fedvalid-20261126.conf
DB=independentai_hub
pkg() { "$1/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'; }
case "${1:-}" in
prepare)
  test ! -e "$NEWV"
  P="$(pkg "$OLDV")/aimarket_hub"
  have="$(for f in config crawler database realm; do echo "$(sha256sum "$P/$f.py" | cut -c1-12) $f.py"; done)"
  want="$(printf 'e2f0eec359c0 config.py\n51757ad16355 crawler.py\ncf228b3f01a9 database.py\n6ff2fc43d197 realm.py')"
  [[ "$have" == "$want" ]] || { echo "unexpected running files:"; echo "$have"; exit 3; }
  cp -a "$OLDV" "$NEWV"
  install -m 644 "$K"/aimarket_hub/{config,crawler,database,realm}.py "$(pkg "$NEWV")/aimarket_hub/"
  find "$(pkg "$NEWV")/aimarket_hub" -name '__pycache__' -prune -exec rm -rf {} +
  ;;
check)
  # The running hub's own environment (EnvironmentFile included), read from /proc; never printed.
  PID="$(systemctl show -p MainPID --value "$UNIT")"
  USR="$(systemctl show -p User --value "$UNIT")"; USR="${USR:-root}"
  install -m 644 "$K/postcheck.py" /tmp/fedvalid-postcheck.py      # the service user cannot read /root
  ENVC="$(mktemp)"; chmod 600 "$ENVC"; cp "/proc/$PID/environ" "$ENVC"; chown "$USR" "$ENVC"
  (cd /tmp && runuser -u "$USR" -- "$NEWV/bin/python" -c 'import os, runpy, sys
env = open(sys.argv[1], "rb").read().decode()
os.environ.update(kv.split("=", 1) for kv in env.split("\0") if "=" in kv)
runpy.run_path(sys.argv[2], run_name="__main__")' "$ENVC" /tmp/fedvalid-postcheck.py); rm -f "$ENVC" /tmp/fedvalid-postcheck.py
  ;;
roll)
  T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /var/backups/independentai
  sudo -u postgres pg_dump -Fc "$DB" > "/var/backups/independentai/hub-pre-fedvalid-$T.dump"
  chmod 600 "/var/backups/independentai/hub-pre-fedvalid-$T.dump"; ls -la "/var/backups/independentai/hub-pre-fedvalid-$T.dump"
  cat > "$DROPIN" <<EOD
[Service]
# 2026-11-26: federated validity bound (AIMARKET_FEDERATED_MAX_UNVERIFIED_S, default 48 h) over hub 3.22.0:
# config.py, crawler.py, database.py, realm.py. Rollback = delete this file, daemon-reload, restart (back to $OLDV via 99h).
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
*) echo "usage: $0 prepare|check|roll|rollback" >&2; exit 2 ;;
esac
