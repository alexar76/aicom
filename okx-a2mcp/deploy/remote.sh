#!/bin/sh
# Runs ON the apex host (factory-vps), from deploy.sh: build the image from /opt/okx-a2mcp and
# replace the running container, keeping the previous one until the new one answers /health.
# Secrets never pass through this script: they are files in /opt/okx-a2mcp-secrets (uid 1000,
# mode 400), mounted read-only, and nothing here prints them.
set -eu
TAG="$1"; PAY_TO="$2"
SECRETS=/opt/okx-a2mcp-secrets
cd /opt/okx-a2mcp
docker build -q -t "okx-a2mcp:$TAG" . >/dev/null
docker network inspect okx-a2mcp >/dev/null 2>&1 || docker network create okx-a2mcp >/dev/null
# The buyer-id HMAC key: generated here once, never leaves the host.
if [ ! -f "$SECRETS/caller_id_secret" ]; then
  umask 077; head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$SECRETS/caller_id_secret"
  chown 1000:1000 "$SECRETS/caller_id_secret"; chmod 400 "$SECRETS/caller_id_secret"
fi
X402=""
[ -f "$SECRETS/cdp_api_key.json" ] && X402="-e CDP_KEY_FILE=/run/secrets/okx/cdp_api_key.json -e X402_PAY_TO=$PAY_TO"
# The hub capability twins (src/hub.js) buy with this credit-account key; without it they are not listed.
[ -f "$SECRETS/hub_api_key" ] && X402="$X402 -e HUB_API_KEY_FILE=/run/secrets/okx/hub_api_key"
# Two HESTIA agents (src/hearth.js) are bought with this seller key on the hearth; without it they are not listed.
[ -f "$SECRETS/hearth_api_key" ] && X402="$X402 -e HEARTH_API_KEY_FILE=/run/secrets/okx/hearth_api_key"
docker rm -f okx-a2mcp-prev >/dev/null 2>&1 || true
if docker inspect okx-a2mcp >/dev/null 2>&1; then docker stop okx-a2mcp >/dev/null; docker rename okx-a2mcp okx-a2mcp-prev; fi
# shellcheck disable=SC2086
docker run -d --name okx-a2mcp --restart unless-stopped --network okx-a2mcp \
  -p 127.0.0.1:9485:9480 -e PUBLIC_URL=https://modelmarket.dev \
  -e CALLER_ID_SECRET_FILE=/run/secrets/okx/caller_id_secret $X402 \
  -v "$SECRETS:/run/secrets/okx:ro" \
  --read-only --tmpfs /tmp:size=16m --cap-drop ALL --security-opt no-new-privileges --memory 256m \
  "okx-a2mcp:$TAG" >/dev/null
for i in 1 2 3 4 5 6 7 8 9 10; do
  if wget -qO- http://127.0.0.1:9485/health >/dev/null 2>&1 || curl -fsS http://127.0.0.1:9485/health >/dev/null 2>&1; then
    echo "okx-a2mcp:$TAG healthy; previous kept stopped as okx-a2mcp-prev"; exit 0
  fi
  sleep 2
done
echo "okx-a2mcp:$TAG did not become healthy; rolling back" >&2
docker logs --tail 20 okx-a2mcp >&2 || true
docker rm -f okx-a2mcp >/dev/null
docker inspect okx-a2mcp-prev >/dev/null 2>&1 && docker rename okx-a2mcp-prev okx-a2mcp && docker start okx-a2mcp >/dev/null
exit 1
