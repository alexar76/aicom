#!/usr/bin/env bash
# Install scripts/docker_logs_reaper.py + its 5-minute timer on docker hosts.
#   scripts/install_docker_logs_reaper.sh admin-vps not-my-vps my-vps competing-lab factory-vps
# admin-vps is reached through not-my-vps (its own sshd is flaky from outside). Re-running is safe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ $# -gt 0 ]] || { echo "usage: $0 HOST..." >&2; exit 2; }

for host in "$@"; do
  jump=()
  [[ "$host" == admin-vps ]] && jump=(-J not-my-vps)
  ssh_=(ssh -o BatchMode=yes -o ConnectTimeout=30 ${jump[@]+"${jump[@]}"} "$host")
  echo "### $host"
  "${ssh_[@]}" 'mkdir -p /usr/local/lib/aicom-ops && cat > /usr/local/lib/aicom-ops/docker_logs_reaper.py && chmod 755 /usr/local/lib/aicom-ops/docker_logs_reaper.py' \
    < "$ROOT/scripts/docker_logs_reaper.py"
  "${ssh_[@]}" 'cat > /etc/systemd/system/docker-logs-reaper.service' < "$ROOT/deploy/docker-logs-reaper.service"
  "${ssh_[@]}" 'cat > /etc/systemd/system/docker-logs-reaper.timer' < "$ROOT/deploy/docker-logs-reaper.timer"
  "${ssh_[@]}" 'python3 -m py_compile /usr/local/lib/aicom-ops/docker_logs_reaper.py \
    && systemctl daemon-reload && systemctl enable --now docker-logs-reaper.timer >/dev/null \
    && systemctl start docker-logs-reaper.service \
    && journalctl -u docker-logs-reaper.service --since -2min --no-pager -o cat | grep -vE "^(Starting|Finished|docker-logs-reaper)" ; \
    systemctl list-timers docker-logs-reaper.timer --no-pager | sed -n 2p'
done
