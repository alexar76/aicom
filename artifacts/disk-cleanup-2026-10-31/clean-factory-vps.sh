#!/usr/bin/env bash
# factory-vps cleanup prepared 2026-10-31 and NOT run: the auto-mode classifier refused it. Owner runs it by hand:
#   scp artifacts/disk-cleanup-2026-10-31/factory-vps-containers-to-remove.txt factory-vps:/root/cleanup-20261031-containers.txt
#   ssh factory-vps bash -s < artifacts/disk-cleanup-2026-10-31/clean-factory-vps.sh
# Removes 168 stopped *-prev containers renamed 2026-10-01..10-25 (hub 66, THEMIS 65, UNI 33, alien 4; every container
# renamed since 10-29 and the newest 2 per service stay), the ai-factory tags brief/visitor-private*/naming/latest/local
# (compose takes AICOM_IMAGE_TAG=perf2-20261023 from .env; the factory runs aicom-security:aicom-app-1-python-20261031),
# dangling images, journal to 500 MB, apt cache. docker rm/rmi refuse anything running or in use.
set -u
echo "before: $(df -h / | tail -1)"
n=0; skipped=0
while read -r name; do
  [ -n "$name" ] || continue
  state=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null) || { skipped=$((skipped+1)); continue; }
  case "$state" in exited|created|dead) docker rm "$name" >/dev/null && n=$((n+1)) ;; *) echo "kept $name ($state)"; skipped=$((skipped+1)) ;; esac
done < /root/cleanup-20261031-containers.txt
echo "removed containers: $n, skipped: $skipped"
for t in brief-20261017 visitor-private2-20261014 visitor-private-20261014 naming-20261014 latest local; do
  docker rmi "ai-factory:$t" >/dev/null 2>&1 && echo "rmi ai-factory:$t" || echo "kept ai-factory:$t (in use or absent)"
done
echo "dangling: $(docker image prune -f 2>&1 | tail -1)"
journalctl --vacuum-size=500M 2>&1 | grep -i freed | tail -2
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
