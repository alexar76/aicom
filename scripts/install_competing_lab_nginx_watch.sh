#!/usr/bin/env bash
# Install nginx self-heal on competing-lab (hunt host).
#
#   ./scripts/install_competing_lab_nginx_watch.sh
#   ./scripts/install_competing_lab_nginx_watch.sh --remote competing-lab
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${1:-}"
if [[ "${1:-}" == "--remote" ]]; then
  REMOTE="${2:?host alias, e.g. competing-lab}"
fi

install_local() {
  install -d /opt/aicom-scripts
  install -m 0755 "$ROOT/scripts/competing_lab_nginx_watch.py" /opt/aicom-scripts/
  install -m 0644 "$ROOT/deploy/aicom-competing-nginx-watch.service" /etc/systemd/system/
  install -m 0644 "$ROOT/deploy/aicom-competing-nginx-watch.timer" /etc/systemd/system/
  install -d /etc/systemd/system/nginx.service.d
  install -m 0644 "$ROOT/deploy/nginx/systemd/nginx-restart-on-failure.conf" \
    /etc/systemd/system/nginx.service.d/restart-on-failure.conf
  systemctl daemon-reload
  systemctl enable --now aicom-competing-nginx-watch.timer
  systemctl restart nginx || systemctl start nginx
  systemctl is-active nginx
  systemctl is-active aicom-competing-nginx-watch.timer
  python3 /opt/aicom-scripts/competing_lab_nginx_watch.py
}

if [[ -n "$REMOTE" ]]; then
  rsync -az \
    "$ROOT/scripts/competing_lab_nginx_watch.py" \
    "$ROOT/deploy/aicom-competing-nginx-watch.service" \
    "$ROOT/deploy/aicom-competing-nginx-watch.timer" \
    "$ROOT/deploy/nginx/systemd/nginx-restart-on-failure.conf" \
    "$REMOTE:/tmp/aicom-nginx-watch/"
  ssh -o BatchMode=yes "$REMOTE" bash <<'REMOTE'
set -euo pipefail
install -d /opt/aicom-scripts /etc/systemd/system/nginx.service.d
install -m 0755 /tmp/aicom-nginx-watch/competing_lab_nginx_watch.py /opt/aicom-scripts/
install -m 0644 /tmp/aicom-nginx-watch/aicom-competing-nginx-watch.service /etc/systemd/system/
install -m 0644 /tmp/aicom-nginx-watch/aicom-competing-nginx-watch.timer /etc/systemd/system/
install -m 0644 /tmp/aicom-nginx-watch/nginx-restart-on-failure.conf \
  /etc/systemd/system/nginx.service.d/restart-on-failure.conf
systemctl daemon-reload
systemctl enable --now aicom-competing-nginx-watch.timer
systemctl restart nginx
systemctl is-active nginx
systemctl is-active aicom-competing-nginx-watch.timer
python3 /opt/aicom-scripts/competing_lab_nginx_watch.py
REMOTE
else
  install_local
fi

echo "OK competing-lab nginx watch installed"
