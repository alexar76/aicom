#!/usr/bin/env bash
# Full ecosystem smoke — Factory, Hub, Mesh, Alien Monitor (all modes), Funnel, Security.
# After redeploy run: ./scripts/deploy_ecosystem.sh (or verify only: this script).
# Hub must be up via ./scripts/deploy_hub.sh — not aimarket-hub/docker compose alone.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
FACTORY="${FACTORY_URL:-http://127.0.0.1:9081}"
FACTORY_INTERNAL="http://127.0.0.1:8081"
FRONTEND="${FRONTEND_URL:-http://127.0.0.1:9080}"
MONITOR="${MONITOR_URL:-http://127.0.0.1:9100}"
HUB="${HUB_URL:-http://127.0.0.1:9083}"
MESH="${MESH_URL:-http://127.0.0.1:8090}"
ARGUS="${ARGUS_URL:-http://127.0.0.1:8787}"
PULSE="${PULSE_URL:-http://127.0.0.1:5199}"
LOTTERY_RELAYER="${LOTTERY_RELAYER_URL:-http://127.0.0.1:9195}"

MESH_AUTH=()
[[ -n "${MESH_API_TOKEN:-}" ]] && MESH_AUTH=(-H "Authorization: Bearer $MESH_API_TOKEN")
MONITOR_AUTH=()
[[ -n "${ALIEN_API_TOKEN:-}" ]] && MONITOR_AUTH=(-H "Authorization: Bearer $ALIEN_API_TOKEN")

PASS=0
FAIL=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name" >&2
    FAIL=$((FAIL + 1))
  fi
}

json_field() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null
}

factory_curl() {
  local path="$1"
  local method="${2:-GET}"
  local data="${3:-}"
  local host_timeout="${FACTORY_CURL_HOST_TIMEOUT:-60}"
  local docker_timeout="${FACTORY_CURL_DOCKER_TIMEOUT:-120}"
  local extra=()
  [[ -n "$data" ]] && extra=(-H 'Content-Type: application/json' -d "$data")
  if curl -sf --max-time "$host_timeout" -X "$method" "${extra[@]}" "$FACTORY$path" 2>/dev/null; then
    return 0
  fi
  docker exec aicom-app-1 curl -sf --max-time "$docker_timeout" -X "$method" "${extra[@]}" "$FACTORY_INTERNAL$path" 2>/dev/null
}

factory_curl_retry() {
  local path="$1"
  local attempts="${2:-3}"
  local pause="${3:-3}"
  local n
  for ((n = 1; n <= attempts; n++)); do
    if factory_curl "$path" >/dev/null; then
      return 0
    fi
    [[ "$n" -lt "$attempts" ]] && sleep "$pause"
  done
  return 1
}

check_factory_products() {
  local n
  for ((n = 1; n <= 3; n++)); do
    if factory_curl /api/products 2>/dev/null | python3 -c "import json,sys; assert 'products' in json.load(sys.stdin)"; then
      return 0
    fi
    sleep 5
  done
  return 1
}

check_factory_all_product_details() {
  FACTORY="$FACTORY" PUBLIC_STOREFRONT_URL="${PUBLIC_STOREFRONT_URL:-https://magic-ai-factory.com}" python3 <<'PY'
import json
import os
import sys
import urllib.request

factory = os.environ["FACTORY"].rstrip("/")
public = os.environ["PUBLIC_STOREFRONT_URL"].rstrip("/")

def fetch(url: str, timeout: int = 120) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")

try:
    _, raw = fetch(f"{factory}/api/products", timeout=120)
    products = json.loads(raw).get("products") or []
except Exception as exc:
    print(f"product list fetch failed: {exc}", file=sys.stderr)
    sys.exit(1)

if not products:
    print("no storefront products", file=sys.stderr)
    sys.exit(1)

api_failures: list[str] = []
page_failures: list[str] = []

for p in products:
    pid = p["id"]
    try:
        _, body = fetch(f"{factory}/api/products/{pid}", timeout=120)
        detail = json.loads(body)
    except Exception as exc:
        api_failures.append(f"{pid}: fetch failed ({exc})")
        continue
    if detail.get("detail"):
        api_failures.append(f"{pid}: {detail.get('detail')}")
        continue
    if not (detail.get("name") or detail.get("idea")):
        api_failures.append(f"{pid}: missing name/idea")
    if "evolution_history" not in detail:
        api_failures.append(f"{pid}: missing evolution_history")
    elif not isinstance(detail["evolution_history"], list):
        api_failures.append(f"{pid}: evolution_history not a list")

    page_url = f"{public}/product/{pid}"
    try:
        code, html = fetch(page_url, timeout=60)
    except Exception as exc:
        page_failures.append(f"{pid}: {exc}")
        continue
    if code != 200:
        page_failures.append(f"{pid}: HTTP {code}")
        continue
    if "Failed to load product" in html or "name 'evolution_history' is not defined" in html:
        page_failures.append(f"{pid}: error text in HTML shell")
    if "AI-Factory" not in html:
        page_failures.append(f"{pid}: missing app shell")

if api_failures:
    print("product detail API failures:", file=sys.stderr)
    for line in api_failures:
        print("  -", line, file=sys.stderr)
    sys.exit(1)

print(f"checked {len(products)} product detail APIs")

if page_failures:
    print("storefront page failures:", file=sys.stderr)
    for line in page_failures:
        print("  -", line, file=sys.stderr)
    sys.exit(1)

print(f"checked {len(products)} storefront pages at {public}")
PY
}

echo "=== Ecosystem full verification ==="
echo "Factory=$FACTORY Monitor=$MONITOR Hub=$HUB"
echo ""

# ── Factory core ──
check "factory /api/health" curl -sf --max-time 20 "$FACTORY/api/health"
check "factory frontend :9080" curl -sf --max-time 15 -o /dev/null "$FRONTEND/"
check "factory /api/products" check_factory_products
check "factory storefront products (all detail APIs + pages)" check_factory_all_product_details
check "factory trust-metrics" factory_curl_retry /api/marketing/trust-metrics
check "security_store in container" docker exec aicom-app-1 test -f /app/data/state/security_store.db

# Funnel lead (dry run — lead capture only, no pipeline product)
LEAD_RESP="$(factory_curl /api/marketing/lead POST '{"email":"ecosystem-verify@example.com","idea":"Ecosystem verification landing for AI scheduling assistant waitlist","source":"verify_script"}' 2>/dev/null || echo '{}')"
echo "$LEAD_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok'), d; assert d.get('status_token')" && { echo "PASS  funnel POST /lead"; PASS=$((PASS+1)); } || { echo "FAIL  funnel POST /lead"; FAIL=$((FAIL+1)); }

# Admin token + funnel dashboard + product P&L
ADMIN_TOKEN="$(docker exec aicom-app-1 python3 -c "
from web.backend.core.security import SecurityManager
print(SecurityManager().create_access_token('admin', role='admin'))
" 2>/dev/null || true)"
if [[ -n "$ADMIN_TOKEN" ]]; then
  check "admin funnel dashboard" docker exec aicom-app-1 curl -sf --max-time 60 -H "Authorization: Bearer $ADMIN_TOKEN" "$FACTORY_INTERNAL/api/admin/funnel/dashboard"
  check "admin product-pnl" docker exec aicom-app-1 curl -sf --max-time 60 -H "Authorization: Bearer $ADMIN_TOKEN" "$FACTORY_INTERNAL/api/admin/finance/product-pnl"
else
  echo "FAIL  admin token generation" >&2
  FAIL=$((FAIL + 2))
fi

# ── Hub ──
check "hub well-known" curl -sf --max-time 10 "$HUB/.well-known/ai-market.json"
check "hub stats/live" curl -sf --max-time 10 "$HUB/ai-market/v2/stats/live?limit=3"
check "hub capital pricing" curl -sf --max-time 10 "$HUB/api/v2/capital/pricing?limit=1"

# ── Mesh ──
check "mesh /v1/stats" curl -sf --max-time 10 "${MESH_AUTH[@]}" "$MESH/v1/stats"

# ── ARGUS ──
check "argus /health" curl -sf --max-time 10 "$ARGUS/health"
ARGUS_HEALTH="$(curl -sf --max-time 10 "$ARGUS/health" || echo '{}')"
echo "$ARGUS_HEALTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('status')=='ok', d
assert 'wallet' not in d, 'H2: /health must not expose wallet'
assert 'chainId' not in d, 'H2: /health must not expose chainId'
" && { echo "PASS  argus /health no wallet leak"; PASS=$((PASS+1)); } || { echo "FAIL  argus /health no wallet leak"; FAIL=$((FAIL+1)); }
ARGUS_STATUS_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$ARGUS/status" || echo 000)"
[[ "$ARGUS_STATUS_CODE" == "401" || "$ARGUS_STATUS_CODE" == "403" ]] && { echo "PASS  argus /status requires token"; PASS=$((PASS+1)); } || { echo "FAIL  argus /status requires token (got $ARGUS_STATUS_CODE)"; FAIL=$((FAIL+1)); }

ARGUS_PUBLIC="${ARGUS_PUBLIC_URL:-https://magic-ai-factory.com/argus/}"
ARGUS_LANDING_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$ARGUS_PUBLIC" || echo 000)"
if [[ "$ARGUS_LANDING_CODE" == "200" ]]; then
  curl -sf --max-time 15 "$ARGUS_PUBLIC" | grep -qiE 'argus|arena|agent' && \
    { echo "PASS  argus public landing $ARGUS_PUBLIC"; PASS=$((PASS+1)); } || \
    { echo "FAIL  argus public landing body unexpected"; FAIL=$((FAIL+1)); }
else
  echo "FAIL  argus public landing (HTTP $ARGUS_LANDING_CODE at $ARGUS_PUBLIC)"
  FAIL=$((FAIL+1))
fi
check "argus /arena/" curl -sf --max-time 15 -o /dev/null "https://magic-ai-factory.com/arena/"

# ── Pulse ──
check "pulse terminal :5199" curl -sf --max-time 10 -o /dev/null "$PULSE/"

# ── Base-path regressions (standalone port + Vite BASE_PATH) ──
check "monitor /monitor/api/health" curl -sf --max-time 10 "$MONITOR/monitor/api/health"
PREF_STATE="$(curl -sf --max-time 60 "${MONITOR_AUTH[@]}" "$MONITOR/monitor/api/state" || echo '{}')"
echo "$PREF_STATE" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert len(d.get('nodes',[])) > 0, d
print('monitor /monitor/api/state nodes', len(d.get('nodes',[])))
" && { echo "PASS  monitor /monitor/api/state"; PASS=$((PASS+1)); } || { echo "FAIL  monitor /monitor/api/state"; FAIL=$((FAIL+1)); }
check "pulse /pulse/ shell" curl -sf --max-time 10 -o /dev/null "$PULSE/pulse/"
check "pulse /pulse/assets in html" bash -c "
  html=\$(curl -sf --max-time 10 '$PULSE/pulse/' || curl -sf --max-time 10 '$PULSE/')
  echo \"\$html\" | grep -qE '/(pulse/)?assets/.+\\.js'
"
PLATON_UI="${PLATON_UI_URL:-http://127.0.0.1:8080}"
if curl -sf --max-time 3 -o /dev/null "$PLATON_UI/platon/" 2>/dev/null; then
  check "platon /platon/ shell" curl -sf --max-time 10 -o /dev/null "$PLATON_UI/platon/"
else
  echo "SKIP  platon /platon/ (not running on $PLATON_UI)"
fi

# ── Alien Monitor UNIVERSE (default) ──
HEALTH="$(curl -sf --max-time 10 "$MONITOR/api/health" || echo '{}')"
echo "$HEALTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('status')=='ok', d
assert d.get('mode')=='universe', d
assert d.get('blockchain_ready') is True, d
print('UNIVERSE mode ok')
" && { echo "PASS  monitor UNIVERSE health"; PASS=$((PASS+1)); } || { echo "FAIL  monitor UNIVERSE health"; FAIL=$((FAIL+1)); }

STATE="$(curl -sf --max-time 60 "${MONITOR_AUTH[@]}" "$MONITOR/api/state" || echo '{}')"
echo "$STATE" | python3 -c "
import json,sys
d=json.load(sys.stdin)
clusters=[n for n in d.get('nodes',[]) if n.get('group')=='cluster']
print('clusters', len(clusters))
" || true

echo "$STATE" | python3 -c "
import json,sys
d=json.load(sys.stdin)
nodes=d.get('nodes',[])
argus=next((n for n in nodes if n.get('id')=='argus'), None)
assert argus, [n.get('id') for n in nodes[:30]]
assert argus.get('group')=='argus', argus
run = argus.get('argus_run')
if run:
    print('argus node', argus.get('label'), 'beats', len(run.get('beats', [])))
else:
    print('argus node', argus.get('label'), 'no live run yet (wire ALIEN_MONITOR_URL on Argus)')
links=d.get('links',[])
assert any(l.get('source')=='argus' for l in links), links[:8]
" && { echo "PASS  monitor argus node"; PASS=$((PASS+1)); } || { echo "FAIL  monitor argus node"; FAIL=$((FAIL+1)); }

echo "$STATE" | python3 -c "
import json,sys
d=json.load(sys.stdin)
nodes=d.get('nodes',[])
family=[n for n in nodes if str(n.get('id','')).startswith('oracle-') and not str(n.get('id','')).startswith('oracle-cave')]
expected={'oracle-platon','oracle-chronos','oracle-lattice','oracle-murmuration','oracle-lumen','oracle-colony','oracle-turing','oracle-percola','oracle-fermat','oracle-ablation','oracle-landauer','oracle-sortes','oracle-gauss','oracle-aestus','oracle-betti','oracle-kantor','oracle-fourier'}
ids={n.get('id') for n in family}
missing=expected-ids
assert not missing, sorted(missing)
assert len(family) >= 17, (len(family), sorted(ids))
print('oracle family', len(family), 'nodes:', ', '.join(sorted(ids)))
" && { echo "PASS  monitor oracle family (17+cave)"; PASS=$((PASS+1)); } || { echo "FAIL  monitor oracle family (17+cave)"; FAIL=$((FAIL+1)); }

# ── Alien Monitor TEST mode (temporary container env) ──
test_mode_probe() {
  local mode="$1"
  docker exec -e "ALIEN_MODE=$mode" alien-monitor python3 -c "
import os, asyncio
os.environ['ALIEN_MODE'] = '$mode'
import main
main.MODE = '$mode'
async def run():
    if main.MODE == 'test':
        s = main.simulator.step()
        assert s.get('summary',{}).get('mode')=='test'
        print('test ok', s['summary'].get('tick'))
    elif main.MODE == 'real':
        d = await main.fetch_real_metrics()
        assert d.get('mode')=='real'
        assert 'nodes' in d
        print('real ok', len(d['nodes']))
    else:
        u = main.get_universe()
        st = u.tick_universe()
        assert 'nodes' in st
        print('universe ok', len(st['nodes']))
asyncio.run(run())
" 2>&1
}

if test_mode_probe test | grep -q 'test ok'; then
  echo "PASS  monitor TEST mode (in-process)"
  PASS=$((PASS + 1))
else
  echo "FAIL  monitor TEST mode" >&2
  FAIL=$((FAIL + 1))
fi

if test_mode_probe real | grep -q 'real ok'; then
  echo "PASS  monitor REAL/LIVE mode (in-process)"
  PASS=$((PASS + 1))
else
  echo "FAIL  monitor REAL mode" >&2
  FAIL=$((FAIL + 1))
fi

if test_mode_probe universe | grep -q 'universe ok'; then
  echo "PASS  monitor UNIVERSE tick (in-process)"
  PASS=$((PASS + 1))
else
  echo "FAIL  monitor UNIVERSE tick" >&2
  FAIL=$((FAIL + 1))
fi

# ── UNI lottery contracts + relayer live feed ──
echo "$HEALTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d.get('contracts') or {}
assert c.get('evm_lottery'), c
print('evm_lottery', c['evm_lottery'])
" && { echo "PASS  monitor evm_lottery deployed"; PASS=$((PASS+1)); } || { echo "FAIL  monitor evm_lottery deployed"; FAIL=$((FAIL+1)); }

check "lottery relayer /healthz" curl -sf --max-time 10 "$LOTTERY_RELAYER/healthz"

STATE2="$(curl -sf --max-time 60 "${MONITOR_AUTH[@]}" "$MONITOR/api/state" || echo '{}')"
echo "$STATE2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
lot=next((n for n in d.get('nodes',[]) if n.get('id')=='lottery'),None)
assert lot, d
m=lot.get('metrics') or {}
assert int(m.get('round') or 0) > 0, m
assert lot.get('group')=='economy', lot
print('lottery round', m.get('round'), 'pool', m.get('prize_pool_usd'))
" && { echo "PASS  monitor live lottery metrics"; PASS=$((PASS+1)); } || { echo "FAIL  monitor live lottery metrics"; FAIL=$((FAIL+1)); }

echo ""
echo "=== Cognition layer (optional remote polls) ==="
DIOSCURI_URL="${ALIEN_DIOSCURI_URL:-${DIOSCURI_URL:-http://127.0.0.1:8790}}"
HELIOS_URL="${ALIEN_HELIOS_URL:-${HELIOS_URL:-http://127.0.0.1:8791}}"
METIS_URL="${ALIEN_METIS_URL:-${METIS_URL:-https://metis.modelmarket.dev}}"

if [[ "${VERIFY_COGNITION:-1}" == "1" ]]; then
  check "DIOSCURI /health" curl -sf --max-time 8 "$DIOSCURI_URL/health"
  check "HELIOS /health" curl -sf --max-time 8 "$HELIOS_URL/health"
  check "METIS /health" curl -sf --max-time 8 "$METIS_URL/health"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
