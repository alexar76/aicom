#!/usr/bin/env bash
# Rebuild and replace the running modelmarket-hub container, preserving its exact
# runtime configuration, with an automatic rollback if the new one does not come up.
#
# Run ON the hub host, from the build tree (default /root/aicom-hub-build).
#
# Why this exists rather than `scripts/deploy_hub.sh`: that script composes the run
# arguments from scratch, and twice now a redeploy has silently dropped the payment
# interlock because those values lived only in the running container's environment and
# nowhere on disk (docs/payment-enable-runbook.md, regressions 2026-07-31 and 2026-08-04).
# This one reads the live container's environment and reuses it verbatim, refuses to
# start if the payment flags did not survive the copy, and keeps the previous container
# so a failed rollout is one command away from being undone.
#
#   ./scripts/deploy_hub_rebuild.sh                 # build, swap, verify, rollback on failure
#   ./scripts/deploy_hub_rebuild.sh --rollback      # put the previous container back
set -euo pipefail

NAME="${AIMARKET_HUB_NAME_CONTAINER:-modelmarket-hub}"
PREV="${NAME}-prev"
PORT="${AIMARKET_HUB_HOST_PORT:-9083}"
BUILD_DIR="${AIMARKET_HUB_BUILD_DIR:-$(pwd)}"
TAG="${AIMARKET_HUB_TAG:-prod-$(date -u +%Y%m%d-%H%M)-mcp}"
IMAGE="modelmarket-hub:${TAG}"
ENV_CAPTURE="${AIMARKET_HUB_ENV_CAPTURE:-/root/hub-runtime.env}"

# Flags whose loss is silent and expensive: the hub keeps answering, it just stops
# charging. Verified in the capture before anything is torn down.
REQUIRED_ENV=(AIFACTORY_PROD AIFACTORY_CRYPTO_ENABLED AIFACTORY_PAYMENT_VERIFY_STUB
              AIFACTORY_PAYMENT_TESTNET AIMARKET_PAYMENT_RECIPIENT AIMARKET_SELLS_FOR)

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

rollback() {
  log "ROLLBACK — restoring the previous container"
  docker rm -f "$NAME" 2>/dev/null || true
  docker rename "$PREV" "$NAME"
  docker start "$NAME"
  for _ in $(seq 1 30); do
    curl -sf "http://127.0.0.1:${PORT}/.well-known/ai-market.json" >/dev/null && {
      log "rolled back and healthy"; return 0; }
    sleep 2
  done
  die "rollback did not come up — the hub is DOWN, investigate by hand"
}

if [[ "${1:-}" == "--rollback" ]]; then
  docker inspect "$PREV" >/dev/null 2>&1 || die "no $PREV container to roll back to"
  rollback
  exit 0
fi

docker inspect "$NAME" >/dev/null 2>&1 || die "$NAME is not running; use scripts/deploy_hub.sh for a first deploy"

# ── 1. Capture the live environment ─────────────────────────────────────────────
log "Capturing the running container's environment → $ENV_CAPTURE"
# Via JSON, not `{{println}}`: a value containing a newline would split across lines, and
# a line-oriented filter then keeps the first fragment and silently drops the rest — a
# truncated secret that still looks like a successful capture. `docker --env-file` cannot
# express such a value at all, so the honest move is to refuse rather than mangle it.
# PATH and the base image's own defaults are dropped: carrying PATH forward from an older
# base image is how a rebuilt container ends up unable to find python.
docker inspect "$NAME" --format '{{json .Config.Env}}' | python3 -c '
import json, re, sys
skip = re.compile(r"^(PATH|HOSTNAME|LANG|GPG_KEY|PYTHON_[A-Z_]+)=")
kept, bad = [], []
for entry in json.load(sys.stdin) or []:
    if skip.match(entry) or "=" not in entry:
        continue
    key, _, value = entry.partition("=")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        continue
    (bad if "\n" in value or "\r" in value else kept).append(key)
    if "\n" not in value and "\r" not in value:
        print(entry)
if bad:
    sys.stderr.write("multi-line values cannot round-trip through --env-file: %s\n" % ", ".join(bad))
    sys.exit(3)
' > "$ENV_CAPTURE" || die "environment capture failed — see the message above; deploy by hand"
chmod 600 "$ENV_CAPTURE"
echo "captured $(wc -l < "$ENV_CAPTURE") variable(s)"

missing=()
for key in "${REQUIRED_ENV[@]}"; do
  # Non-empty, not merely present: `AIMARKET_SELLS_FOR=` passes a presence test and means
  # "this hub sells for nobody", which serves every federated capability free while the
  # manifest still reports payment_configured — the 2026-08-04 regression exactly.
  grep -qE "^${key}=.+" "$ENV_CAPTURE" || missing+=("$key")
done
if (( ${#missing[@]} )); then
  die "payment interlock variables absent from the capture: ${missing[*]}
The running hub may already be serving paid capabilities for free. Fix that first
(docs/payment-enable-runbook.md) rather than baking the gap into a new container."
fi
log "payment interlock present in capture — safe to proceed"

# Persist the payment subset where deploy_hub.sh looks for it, so the NEXT redeploy by
# any route keeps these values instead of rediscovering the same regression.
PAYMENT_ENV="${BUILD_DIR}/deploy/hub-payment.env"
mkdir -p "${BUILD_DIR}/deploy"
grep -E '^(AIFACTORY_PROD|AIFACTORY_CRYPTO_ENABLED|AIFACTORY_PAYMENT_|AIMARKET_PAYMENT_|AIMARKET_ESCROW_|AIMARKET_SELLS_FOR|AIFACTORY_AI_MARKET_CONTRACT|AIMARKET_ALLOW_DEMO_CREDIT)' \
  "$ENV_CAPTURE" > "$PAYMENT_ENV" || true
chmod 600 "$PAYMENT_ENV"
echo "payment env mirrored → $PAYMENT_ENV ($(wc -l < "$PAYMENT_ENV") lines)"

# ── 2. Build ────────────────────────────────────────────────────────────────────
log "Building $IMAGE from $BUILD_DIR"
cd "$BUILD_DIR"
[[ -f aimarket-hub/Dockerfile ]] || die "no aimarket-hub/Dockerfile under $BUILD_DIR"
docker build -f aimarket-hub/Dockerfile -t "$IMAGE" .

# ── 3. Swap, keeping the old container for rollback ─────────────────────────────
# Which peer the hub will actually see. nginx talks to 127.0.0.1:9083 on the host, docker
# DNATs that into the container, and the address arriving inside is the network's gateway —
# NOT 127.0.0.1. The hub matches AIMARKET_TRUSTED_PROXIES by exact string, so naming the
# wrong one makes it ignore every forwarded header and attribute the whole internet to a
# single address: one shared rate-limit bucket and one shared trial identity.
GATEWAY_IP="$(docker network inspect aicom_aicom_net \
  --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | tr -d '[:space:]')"
TRUSTED="${AIMARKET_TRUSTED_PROXIES:-}"
if [[ -z "$TRUSTED" ]]; then
  TRUSTED="127.0.0.1${GATEWAY_IP:+,$GATEWAY_IP}"
fi
[[ -n "$GATEWAY_IP" ]] || echo "WARN: could not read the aicom_aicom_net gateway address;
     forwarded headers may be ignored and every caller merged into one bucket. Set
     AIMARKET_TRUSTED_PROXIES explicitly and re-run." >&2
log "Trusted proxies for the new container: $TRUSTED"

# Seller-of-record list. Captured verbatim by default; overridable because the capture is
# the only copy that exists and a satellite added to the catalogue after the last deploy is
# invisible to it — atlas was served free for exactly that reason. Announced either way, so
# the value is on the deploy log rather than only inside a container.
SELLS_FOR="${AIMARKET_SELLS_FOR:-$(grep -E '^AIMARKET_SELLS_FOR=' "$ENV_CAPTURE" | head -1 | cut -d= -f2-)}"
[[ -n "$SELLS_FOR" ]] || die "AIMARKET_SELLS_FOR resolved empty — every federated capability would be served free"
log "Seller of record for: $SELLS_FOR"

log "Swapping containers"
docker rm -f "$PREV" 2>/dev/null || true
# Refuse rather than tear down the live hub into a state the rollback cannot reach: if the
# name is still taken, `docker rename` below fails AFTER the stop and set -e exits with the
# site down. Checked while everything is still running.
if docker inspect "$PREV" >/dev/null 2>&1; then
  die "$PREV still exists and could not be removed — clear it by hand before deploying"
fi
docker stop "$NAME"
if ! docker rename "$NAME" "$PREV"; then
  docker start "$NAME" || true
  die "could not rename the running container; it has been restarted unchanged"
fi

set +e
docker run -d --name "$NAME" --restart unless-stopped \
  --network aicom_aicom_net \
  --env-file "$ENV_CAPTURE" \
  -e AIMARKET_TRUSTED_PROXIES="$TRUSTED" \
  -e AIMARKET_SELLS_FOR="$SELLS_FOR" \
  -p "127.0.0.1:${PORT}:9083" \
  -v modelmarket_hub_data:/app/data \
  -v /root/claudecode/aicom/data:/factory_data:ro \
  "$IMAGE"
started=$?
set -e
(( started == 0 )) || { rollback; die "docker run failed"; }

# ── 4. Verify before declaring success ──────────────────────────────────────────
log "Waiting for health"
healthy=0
for _ in $(seq 1 45); do
  if curl -sf "http://127.0.0.1:${PORT}/.well-known/ai-market.json" >/dev/null; then healthy=1; break; fi
  sleep 2
done
(( healthy )) || { docker logs --tail 40 "$NAME" || true; rollback; die "new container never became healthy"; }

fail=""
curl -sf "http://127.0.0.1:${PORT}/.well-known/ai-market.json" \
  | grep -q '"payment_configured": *true' || fail="payment_configured is not true"
curl -sf "http://127.0.0.1:${PORT}/mcp" | grep -q '"service": *"aimarket-hub-mcp"' \
  || fail="${fail:+$fail; }apex /mcp does not answer"
# The JSON-RPC surface, not just the info document: a gateway can answer GET perfectly
# while every tools/call raises, and that is the half strangers actually use.
curl -sf -X POST "http://127.0.0.1:${PORT}/mcp" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | grep -q 'market_invoke' || fail="${fail:+$fail; }/mcp tools/list does not list market_invoke"
curl -sf "http://127.0.0.1:${PORT}/mcp" | grep -q '"trial": *"per-caller"' \
  || fail="${fail:+$fail; }the trial tier is off — every newcomer meets the payment wall"
# Every declared peer must actually charge. `payment_configured` says nothing about this,
# and a peer silently missing from the list is the failure that took a month to notice.
for peer in ${SELLS_FOR//,/ }; do
  cap="$(curl -sf "http://127.0.0.1:${PORT}/ai-market/v2/prices" \
    | python3 -c "
import json,sys
peer='${peer}'.rstrip('/')
rows=[r for r in (json.load(sys.stdin).get('prices') or [])
      if (r.get('source_hub') or '').rstrip('/')==peer and (r.get('price_usd') or 0)>0]
if rows:
    r=min(rows, key=lambda x: x['price_usd'])
    print('%s|%s' % (r['product_id'], r['capability_id']))
" 2>/dev/null)"
  [[ -n "$cap" ]] || continue
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:${PORT}/ai-market/v2/invoke" \
    -H 'content-type: application/json' \
    -d "{\"product_id\":\"${cap%%|*}\",\"capability_id\":\"${cap##*|}\",\"source_hub\":\"${peer}\",\"input\":{}}")"
  [[ "$code" == "402" ]] || fail="${fail:+$fail; }${peer} serves priced work for HTTP ${code}, not 402"
done
if [[ -n "$fail" ]]; then
  echo "POST-DEPLOY CHECK FAILED: $fail" >&2
  rollback
  die "rolled back: $fail"
fi

log "OK — $IMAGE is live, previous container kept as $PREV"
echo "roll back with: $0 --rollback"
echo "discard the old one with: docker rm $PREV"
