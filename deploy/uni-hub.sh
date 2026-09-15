#!/usr/bin/env bash
# Bring up the UNI hub — the sealed bubble's own AIMarket hub.
#
# Bound to 127.0.0.1 only; reachable from outside solely through the nginx vhost in
# deploy/nginx/uni.modelmarket.dev.conf, which answers on its OWN name. Every amount it
# reports is virtual, so what protects the reader is that name: a separate subdomain, never a
# path under the live host. The realm seal stops it reaching a real chain; the separate
# identity stops the real world reading it as real.
#
# Reuses the image the live hub already runs (same code, different realm) — the whole claim
# of UNI is that nothing inside differs, so a bubble-specific build would defeat the point.
set -euo pipefail

IMAGE="${1:?usage: deploy_uni_hub.sh <image> <token> <escrow>}"
TOKEN="${2:?token address}"
ESCROW="${3:?escrow address}"

# Public identity of the bubble. Everything the hub advertises is built from this, so an
# operator who changes it changes the manifest, the MCP endpoint and the receipts together.
HUB_URL="${HUB_URL:-https://uni.modelmarket.dev}"
# No default. The old value was a constant published in this repository, which was harmless
# only while nothing could reach the port; it stopped being harmless the moment the vhost
# existed. Generate one: `openssl rand -base64 32`.
ADMIN_TOKEN="${ADMIN_TOKEN:?set ADMIN_TOKEN — the bubble is publicly reachable}"

# The bubble's own capability satellites (deploy/uni-satellites.sh). Two things depend on
# naming them here, and both fail silently otherwise:
#
#  * an EMPTY AIMARKET_SEED_LIST is NOT an empty seed list. `config._parse_seed_list` treats
#    an empty env var as unset and falls back to the committed federation_seeds.json — the six
#    REAL satellites, with pinned keys that grant trusted-and-indexed on FIRST contact. The
#    bubble ran that way and published those hostnames in its own well-known. The realm seal
#    now refuses an outside seed at startup, so this must be right or the hub will not boot.
#  * the periodic crawl needs BOTH auto-crawl and a non-empty seed list; with neither, the
#    bounded refresh pass over active peers never runs either and the catalogue stays empty.
SATELLITES="${SATELLITES:-khronos kyma psephos stoicheion diktyon horizon}"
SEED_LIST=""
SEED_PUBKEYS="{}"
for name in $SATELLITES; do
  SEED_LIST="${SEED_LIST:+$SEED_LIST,}${HUB_URL}/sat/${name}/.well-known/ai-market.json"
done
# Keys are read from the satellites themselves: a pin that does not match what the peer
# advertises reads as a takeover for good (status=key_mismatch, every later crawl returns
# None) and the only exits are /federation/peers/repin or a second admin announce.
if command -v python3 >/dev/null; then
  SEED_PUBKEYS="$(HUB_URL="$HUB_URL" SATELLITES="$SATELLITES" python3 - <<'PYKEYS'
import json, os, urllib.request
ports = {"khronos": 9301, "kyma": 9302, "psephos": 9303,
         "stoicheion": 9304, "diktyon": 9305, "horizon": 9306}
base = os.environ["HUB_URL"].rstrip("/")
out = {}
for name in os.environ["SATELLITES"].split():
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{ports[name]}/.well-known/ai-market.json", timeout=5) as r:
            key = json.load(r).get("signer_public_key")
    except Exception:
        continue
    if key:
        out[f"{base}/sat/{name}/.well-known/ai-market.json"] = key
print(json.dumps(out, separators=(",", ":")))
PYKEYS
)"
fi

# Seller of record for those satellites. Without this the economics stay broker-shaped — the
# peer bills the buyer and this hub takes only its routing fee — and a satellite that does not
# bill at all (none of them do) is free to call while advertising a price. Measured: 51
# successful "paid" invokes charged the buyer $0.00. Declared, never inferred.
SELLS_FOR=""
for name in $SATELLITES; do
  SELLS_FOR="${SELLS_FOR:+$SELLS_FOR,}${HUB_URL}/sat/${name}"
done

HUB_WALLET="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"   # Anvil #1 — the bubble's hub
HUB_KEY="0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
PORT="9183"
NAME="modelmarket-hub-uni"

# RPC is the docker bridge address, served by uni-rpc-bridge.service: `--add-host
# host.docker.internal:host-gateway` is unsupported by this docker version (it lands in
# /etc/hosts as the literal string "invalid IP"), and Anvil listens on the host loopback
# only — deliberately, so the bubble chain is unreachable from off-host.
# AIMARKET_ALLOW_LOCAL_PUBLISH: inside a sealed bubble there is no public https endpoint to
# publish, because there is no public anything. This is the guard's own documented opt-in
# rather than a code change — the SSRF rule stays exactly as strict on every hub that is not
# the bubble, and the two ufw rules that let containers reach 172.17.0.1 are scoped to the
# docker bridge, so none of this is reachable from off-host.
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker volume create modelmarket_hub_uni_data >/dev/null

docker run -d --name "$NAME" \
  --restart unless-stopped \
  -p "127.0.0.1:${PORT}:9083" \
  -v modelmarket_hub_uni_data:/app/data \
  \
  -e AIMARKET_CHAIN_REALM=uni \
  -e AIMARKET_UNI_CHAIN_ID=31337 \
  -e AIMARKET_RPC_BASE=http://172.17.0.1:8546 \
  -e AIMARKET_ADDR_BASE_USDC="$TOKEN" \
  -e AIMARKET_ADDR_BASE_AIMARKETESCROW="$ESCROW" \
  \
  -e AIFACTORY_CRYPTO_ENABLED=1 \
  -e AIFACTORY_PROD=1 \
  -e AIFACTORY_PAYMENT_TESTNET=0 \
  -e AIFACTORY_PAYMENT_VERIFY_STUB=0 \
  -e AIMARKET_ALLOW_DEMO_CREDIT=0 \
  -e AIMARKET_PAYMENT_RECIPIENT="$HUB_WALLET" \
  -e AIMARKET_PAYMENT_CHAIN=base \
  -e AIMARKET_PAYMENT_TOKENS=USDC \
  \
  -e AIMARKET_ESCROW_BRIDGE_ENABLED=1 \
  -e AIMARKET_ESCROW_NETWORK=base \
  -e AIMARKET_ESCROW_CONTRACT="$ESCROW" \
  -e AIMARKET_ESCROW_EVM_ADDRESS="$ESCROW" \
  -e AIMARKET_ESCROW_HUB_ADDRESS="$HUB_WALLET" \
  -e AIMARKET_ESCROW_PRIVATE_KEY="$HUB_KEY" \
  -e AIMARKET_ESCROW_SUBMIT_STRATEGY=env \
  -e AIMARKET_ESCROW_SUBMIT_CONFIRM=i-understand-this-moves-funds \
  \
  -e AIMARKET_X402_ACCEPT=1 \
  -e AIMARKET_X402_PAY_TO="$HUB_WALLET" \
  -e AIMARKET_X402_CHAIN=base \
  -e AIMARKET_X402_ASSET="$TOKEN" \
  -e AIMARKET_X402_MAX_UNSETTLED_USD=1000 \
  \
  -e AIMARKET_HUB_NAME=modelmarket.dev \
  -e AIMARKET_HUB_URL="$HUB_URL" \
  -e AIMARKET_ADMIN_TOKEN="$ADMIN_TOKEN" \
  -e AIMARKET_ORACLE_FAMILY_URL=off \
  -e AIMARKET_AUTO_CRAWL=1 \
  -e AIMARKET_SEED_LIST="$SEED_LIST" \
  -e AIMARKET_SEED_PUBKEYS="$SEED_PUBKEYS" \
  -e AIMARKET_SELLS_FOR="$SELLS_FOR" \
  -e AIMARKET_TRUSTED_PROXIES=127.0.0.1 \
  -e AIMARKET_INVOKE_HOST_GATEWAY=172.17.0.1 \
  -e AIMARKET_ALLOW_LOCAL_PUBLISH=1 \
  -e AIMARKET_CREDITS_ENABLED=1 \
  -e AIMARKET_CREDITS_FREE_GRANT_USD=0 \
  -e AIMARKET_PUBLISHER_SHARE_BPS=7000 \
  "$IMAGE" >/dev/null

echo "started $NAME on 127.0.0.1:${PORT}, public at $HUB_URL"
sleep 10
docker logs "$NAME" 2>&1 | grep -iE "realm|SEALED|breach|crypto|Traceback" | head -12 || true
echo "--- health ---"
curl -s -o /dev/null -w "http %{http_code}\n" --max-time 10 "http://127.0.0.1:${PORT}/ai-market/v2/stats/live" || true
