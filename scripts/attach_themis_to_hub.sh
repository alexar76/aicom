#!/usr/bin/env bash
# Re-create the THEMIS container inside the Hub container's network namespace.
#
# Why this script has to exist. The Hub calls the admission auditor at
# http://127.0.0.1:8080/invoke, and that address is not a convenience: the Hub's SSRF guard
# (`supply_chain_admission._validate_endpoint`) exempts loopback and nothing else — every
# other host must clear `crawler._url_is_safe`, which blocks RFC1918. So the docker network
# gateway, the bridge IP and any container name are all refused, and the only way the Hub can
# reach a co-located auditor is to share its network namespace.
#
# The consequence is a coupling that is invisible until it breaks: `--network container:<hub>`
# pins THEMIS to one specific container ID. Recreate the Hub and THEMIS keeps running, keeps
# reporting healthy (its healthcheck talks to itself), and is unreachable by anything —
# including the Hub. That is exactly the state found on 2026-08-24: THEMIS was attached to a
# container that no longer existed, so supply-chain admission had been silently degraded
# since the previous Hub redeploy.
#
# Therefore: every Hub swap must be followed by this script, and deploy_hub_rebuild.sh calls
# it automatically. Run it by hand after any manual `docker run` of the Hub.
#
#   ./scripts/attach_themis_to_hub.sh            # attach to the running modelmarket-hub
#   THEMIS_IMAGE=themis:prod-x ./scripts/...     # pin a different image
set -euo pipefail

HUB="${AIMARKET_HUB_NAME_CONTAINER:-modelmarket-hub}"
NAME="${THEMIS_CONTAINER:-themis}"
VOLUME="${THEMIS_VOLUME:-themis_data}"

die() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '=== %s\n' "$*"; }

docker inspect "$HUB" >/dev/null 2>&1 || die "$HUB is not running — start the Hub first"
HUB_ID="$(docker inspect "$HUB" --format '{{.Id}}')"
HUB_STATE="$(docker inspect "$HUB" --format '{{.State.Status}}')"
[[ "$HUB_STATE" == "running" ]] || die "$HUB is $HUB_STATE, not running"

# Reuse the image THEMIS is already on unless told otherwise: this script re-homes a
# container's network, it is not a deploy and must not silently change the code that runs.
if [[ -n "${THEMIS_IMAGE:-}" ]]; then
  IMAGE="$THEMIS_IMAGE"
elif docker inspect "$NAME" >/dev/null 2>&1; then
  IMAGE="$(docker inspect "$NAME" --format '{{.Config.Image}}')"
else
  die "no $NAME container to read an image from; pass THEMIS_IMAGE=…"
fi

CURRENT=""
if docker inspect "$NAME" >/dev/null 2>&1; then
  CURRENT="$(docker inspect "$NAME" --format '{{.HostConfig.NetworkMode}}')"
fi
RUNNING_IMAGE=""
if docker inspect "$NAME" >/dev/null 2>&1; then
  RUNNING_IMAGE="$(docker inspect "$NAME" --format '{{.Config.Image}}')"
fi
# Skip only when the namespace matches, the image matches, AND the auditor actually
# answers. Checking the namespace alone made THEMIS_IMAGE a no-op whenever the container
# happened to be correctly homed — which is most of the time, so a rebuilt image would
# silently never be rolled out and the routes it added would stay missing.
#
# The liveness half was added after a measurement on 2026-08-25: a plain
# `docker restart modelmarket-hub` recreates the Hub's network sandbox, and THEMIS keeps a
# handle on the old one. Its `NetworkMode` still reads `container:<same id>` and its image
# is unchanged, so both string checks passed while the auditor was unreachable for as long
# as anyone cared to wait — measured 30s of `000` from the host, cured only by restarting
# THEMIS. A re-homing script that skips exactly when re-homing is needed is worse than
# none, because the deploy it runs from reports success.
themis_answers() {
  docker exec "$HUB" python3 -c "
import sys, urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1
}
if [[ "$CURRENT" == "container:$HUB_ID" && "$RUNNING_IMAGE" == "$IMAGE" ]]; then
  if themis_answers; then
    log "$NAME is already in $HUB's namespace on $IMAGE and answering — nothing to do"
    exit 0
  fi
  log "$NAME claims $HUB's namespace on $IMAGE but does not answer — re-homing anyway"
fi
if [[ "$CURRENT" == "container:$HUB_ID" ]]; then
  log "namespace is correct; recreating anyway to move $RUNNING_IMAGE -> $IMAGE"
fi
log "re-homing $NAME: $CURRENT  ->  container:$HUB_ID"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped \
  --network "container:$HUB_ID" \
  -e HOST=0.0.0.0 \
  -e AIMARKET_PROVIDER_IDENTITY_FILE=/data/provider.key \
  -v "${VOLUME}:/data" \
  "$IMAGE" >/dev/null

log "waiting for the auditor to answer inside the Hub's namespace"
for _ in $(seq 1 30); do
  if docker exec "$HUB" python3 -c "
import sys, urllib.request
try:
    urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    log "OK — the Hub reaches the auditor on loopback again"
    docker exec "$HUB" python3 -c "
import json, urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read().decode()[:200])
" || true
    exit 0
  fi
  sleep 2
done
docker logs --tail 30 "$NAME" || true
die "$NAME never answered on 127.0.0.1:8080 inside $HUB — admission is still degraded"
