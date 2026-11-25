#!/usr/bin/env bash
# Actor proof v2 on attested (main c3e0fa82e, 2026-10-25): every Attested service and the
# attestedmemory.net pages switch together. Run on the attested host as root, from
# /root/actorv2-kit-20261125 after the eight images below are built (see ROLLOUT.md).
# Between the first and the last swap (about two minutes) a browser that still holds the
# old pages, or a v1 caller, gets 401; a reload fetches the new pages (Cache-Control: no-cache).
set -euo pipefail
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
KIT=/root/actorv2-kit-20261125
ROLL=/root/security-20261031/rollout_container.py
HUB=/opt/aicom/attested/attested-memory-hub
SAAS=/opt/aicom/attested/deploy
LANDING=/opt/aicom/saas-landing
BACKUP=/root/actorv2-backup-$STAMP

for image in attested-memory-hub-memory-market:actorv2-20261125 \
    aicom-security:aicom-saas-gateway-actorv2-20261125 aicom-security:aicom-personal-memory-actorv2-20261125 \
    aicom-security:aicom-team-memory-actorv2-20261125 aicom-security:aicom-expert-market-actorv2-20261125 \
    aicom-security:attested-deal-actorv2-20261125 aicom-security:attested-meter-actorv2-20261125 \
    aicom-security:attested-prove-actorv2-20261125; do
  docker image inspect "$image" >/dev/null   # refuse before anything changes
done

mkdir -p "$BACKUP/landing"
cp "$HUB/docker-compose.yml" "$BACKUP/memory-hub-docker-compose.yml"
cp "$SAAS/compose.yml" "$BACKUP/attested-deploy-compose.yml"
for f in actor.js checkout.js developer.js memory.js team.js developers.html; do cp -p "$LANDING/$f" "$BACKUP/landing/$f"; done
echo "backup: $BACKUP"

# 1. Memory Market (Compose pin, as the atlas rollout of 2026-11-24).
sed -i 's|image: attested-memory-hub-memory-market:atlas-20261124 .*|image: attested-memory-hub-memory-market:actorv2-20261125  # 2026-11-25: actor proof v2 over atlas-20261124 (rollback: atlas-20261124)|' "$HUB/docker-compose.yml"
grep -q 'memory-market:actorv2-20261125' "$HUB/docker-compose.yml"
(cd "$HUB" && docker compose up -d --no-deps memory-market)
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:8810/healthz >/dev/null 2>&1 && break; sleep 2; done
curl -fsS http://127.0.0.1:8810/healthz >/dev/null

# 2. Gateway and the three product shells: the 2026-10-31 swap script keeps env, networks
#    and ports, and leaves NAME-security-prev-<ns> stopped for rollback.
python3 "$ROLL" aicom-saas-gateway-1   --image aicom-security:aicom-saas-gateway-actorv2-20261125   --health http://127.0.0.1:9400/healthz
python3 "$ROLL" aicom-personal-memory-1 --image aicom-security:aicom-personal-memory-actorv2-20261125 --health http://127.0.0.1:9410/healthz
python3 "$ROLL" aicom-team-memory-1    --image aicom-security:aicom-team-memory-actorv2-20261125    --health http://127.0.0.1:9420/healthz
python3 "$ROLL" aicom-expert-market-1  --image aicom-security:aicom-expert-market-actorv2-20261125  --health http://127.0.0.1:9430/healthz

# 3. The pages that sign in the browser.
for f in actor.js checkout.js developer.js memory.js team.js developers.html; do
  install -m 0644 -o 501 -g staff "$KIT/landing/$f" "$LANDING/$f"
done

# 4. Deal, Meter, Prove: same swap, and the Compose pins follow so a later `up` keeps v2.
python3 "$ROLL" attested-saas-deal-1  --image aicom-security:attested-deal-actorv2-20261125  --health http://127.0.0.1:9440/healthz
python3 "$ROLL" attested-saas-meter-1 --image aicom-security:attested-meter-actorv2-20261125 --health http://127.0.0.1:9450/healthz
python3 "$ROLL" attested-saas-prove-1 --image aicom-security:attested-prove-actorv2-20261125 --health http://127.0.0.1:9460/healthz
sed -i -e 's|aicom-security:attested-deal-signature-20261108t073311z|aicom-security:attested-deal-actorv2-20261125|' \
       -e 's|aicom-security:attested-meter-signature-20261108t073311z|aicom-security:attested-meter-actorv2-20261125|' \
       -e 's|aicom-security:attested-prove-signature-20261108t073311z|aicom-security:attested-prove-actorv2-20261125|' "$SAAS/compose.yml"

docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'memory-market|saas-gateway|personal-memory|team-memory|expert-market|saas-deal|saas-meter|saas-prove'
echo "done; rollback: $KIT/rollback.sh $BACKUP"
