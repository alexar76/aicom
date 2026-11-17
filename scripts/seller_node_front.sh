#!/usr/bin/env bash
# (Re)create a seller node's federation front (`aimarket node serve`) on factory-vps, signing hybrid.
#
#   scp scripts/seller_node_front.sh factory-vps:/root/ && ssh factory-vps 'bash /root/seller_node_front.sh esim'
#   ssh factory-vps 'bash /root/seller_node_front.sh domains'
#   ssh factory-vps 'bash /root/seller_node_front.sh --check esim'     # verify only, change nothing
#
# Why it exists (2026-11-15): the fronts of esim.modelmarket.dev and domains.modelmarket.dev were started
# by hand without AIMARKET_PQC=1, so they signed Ed25519 only, and hub.attestedmemory.net (which requires a
# post-quantum signature) kept both pending for weeks while every other check was green. This script is the
# one place that says how a front runs: always hybrid, always hardened, the same for every front.
#
# Per front:
#   - verifies the running front; if it already signs hybrid (manifest and well-known) it stops there;
#   - backs up the front's data dir (identity keys) to /root/<name>-data-<UTC>.tgz;
#   - keeps the old container as <name>-prev (stopped) and starts the new one with the same image,
#     network, port and mounts plus AIMARKET_PQC=1 and the hardening flags;
#   - verifies the new front with the hub's own code under AIMARKET_PQC_REQUIRE=1; on any failure it
#     removes the new container and starts the old one again;
#   - backs the data dir up again, now with the ML-DSA-65 key (peers pin it: losing it = a new identity).
set -euo pipefail

CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then CHECK_ONLY=1; shift; fi
case "${1:-}" in
  esim)    name=esim-federation    image=aicom-security:esim-federation-hc-live-20261031    net=esim-rails  port=9494 dir=/opt/esim-federation ;;
  domains) name=domains-federation image=aicom-security:domains-federation-hc-live-20261031 net=domains-net port=9496 dir=/opt/domains-federation ;;
  *) echo "usage: $0 [--check] esim|domains" >&2; exit 2 ;;
esac

verify() {  # $1 = container; exit 0 only if well-known and manifest both verify as hybrid
  docker exec -i -e AIMARKET_PQC_REQUIRE=1 "$1" python - <<'PY'
import json, sys, time, urllib.request
from aimarket_hub.signing import Signer
def get(path):
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:9090{path}", timeout=5) as r:
                return json.load(r)
        except Exception:
            time.sleep(2)
    sys.exit(f"no answer on {path}")
wk = get("/.well-known/ai-market.json")
man = get("/ai-market/v2/manifest")
key = wk.get("signer_public_key") or ""
ok_wk = bool((wk.get("signature") or {}).get("pq_value")) and Signer.verify_object_signature(wk, key)
ok_man = bool((man.get("signature") or {}).get("pq_value")) and Signer("/tmp/verifier_key", pqc=False).verify_manifest_signature(man, key)
print(f"well-known hybrid={ok_wk} manifest hybrid={ok_man} key={key[:12]}")
sys.exit(0 if ok_wk and ok_man else 1)
PY
}

if verify "$name"; then echo "$name already signs hybrid"; exit 0; fi
if [[ "$CHECK_ONLY" -eq 1 ]]; then echo "$name signs classic-only"; exit 1; fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tar -czf "/root/${name}-data-${stamp}.tgz" -C "$dir" data
echo "backup: /root/${name}-data-${stamp}.tgz"

docker rm -f "${name}-prev" >/dev/null 2>&1 || true
docker stop "$name" >/dev/null
docker rename "$name" "${name}-prev"
rollback() {
  echo "verification failed; restoring ${name}-prev" >&2
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker rename "${name}-prev" "$name"
  docker start "$name" >/dev/null
}
trap rollback ERR
docker run -d --name "$name" --restart unless-stopped --network "$net" \
  -p "127.0.0.1:${port}:9090" --user 1000 --read-only --tmpfs /tmp:size=16m \
  --cap-drop ALL --security-opt no-new-privileges --memory 256m \
  -e AIMARKET_PQC=1 \
  -v "$dir/data:/node/data:rw" -v "$dir/node.toml:/node/node.toml:ro" \
  "$image" >/dev/null
verify "$name"
trap - ERR
tar -czf "/root/${name}-data-${stamp}-hybrid.tgz" -C "$dir" data
echo "$name signs hybrid; rollback: ${name}-prev (stopped); keys: /root/${name}-data-${stamp}-hybrid.tgz"
