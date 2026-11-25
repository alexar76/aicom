#!/usr/bin/env bash
# Return every service to the image it ran before apply.sh, and the pages to their copies.
# Usage: rollback.sh /root/actorv2-backup-<stamp>
# The actor_proof_nonces_v2 tables the new code created stay; the old code never reads them.
set -euo pipefail
BACKUP=${1:?backup folder printed by apply.sh}
ROLL=/root/security-20261031/rollout_container.py
HUB=/opt/aicom/attested/attested-memory-hub
SAAS=/opt/aicom/attested/deploy
LANDING=/opt/aicom/saas-landing

cp "$BACKUP/memory-hub-docker-compose.yml" "$HUB/docker-compose.yml"
(cd "$HUB" && docker compose up -d --no-deps memory-market)

swap() {  # container image port
  if docker inspect "$1" --format '{{.Config.Image}}' | grep -q actorv2-20261125; then
    python3 "$ROLL" "$1" --image "$2" --health "http://127.0.0.1:$3/healthz"
  fi
}
swap aicom-saas-gateway-1    aicom-security:aicom-saas-gateway-1-hc-live-20261031    9400
swap aicom-personal-memory-1 aicom-security:aicom-personal-memory-1-hc-live-20261031 9410
swap aicom-team-memory-1     aicom-security:aicom-team-memory-1-hc-live-20261031     9420
swap aicom-expert-market-1   aicom-security:aicom-expert-market-1-hc-live-20261031   9430
swap attested-saas-deal-1    aicom-security:attested-deal-signature-20261108t073311z  9440
swap attested-saas-meter-1   aicom-security:attested-meter-signature-20261108t073311z 9450
swap attested-saas-prove-1   aicom-security:attested-prove-signature-20261108t073311z 9460
cp "$BACKUP/attested-deploy-compose.yml" "$SAAS/compose.yml"
for f in "$BACKUP"/landing/*; do install -m 0644 -o 501 -g staff "$f" "$LANDING/$(basename "$f")"; done
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'memory-market|saas-gateway|personal-memory|team-memory|expert-market|saas-deal|saas-meter|saas-prove'
