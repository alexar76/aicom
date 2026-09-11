#!/usr/bin/env bash
# Verify UNI virtual universe + hub integration after deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONITOR_URL="${ALIEN_MONITOR_URL:-http://127.0.0.1:9100}"
HUB_URL="${AIMARKET_HUB_URL:-http://127.0.0.1:9083}"

echo "== UNI ecosystem verification =="
echo "Monitor: $MONITOR_URL"
echo "Hub:     $HUB_URL"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

# Alien monitor health
health="$(curl -sf "$MONITOR_URL/api/health" 2>/dev/null || curl -sf "$MONITOR_URL/health" 2>/dev/null || true)"
if [[ -z "$health" ]]; then
  fail "alien-monitor not reachable at $MONITOR_URL"
fi
echo "$health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
mode=d.get('mode') or d.get('universe',{}).get('mode')
bc=d.get('blockchain_ready') or d.get('universe',{}).get('blockchain_ready')
boot=d.get('bootstrap') or d.get('universe',{}).get('bootstrap') or {}
if mode!='universe':
    sys.exit('mode is %s, expected universe'%mode)
if not bc:
    sys.exit('blockchain_ready is false')
if isinstance(boot,dict) and boot.get('ok') is False:
    sys.exit('bootstrap failed: %s'%boot)
print('monitor: mode=%s blockchain_ready=%s'%(mode,bc))
" || fail "monitor health checks"
ok "alien-monitor universe health"

# Hub well-known + sandbox quota
curl -sf "$HUB_URL/.well-known/ai-market.json" >/dev/null || fail "hub well-known"
ok "hub well-known"

quota="$(curl -sf "$HUB_URL/ai-market/v2/sandbox/quota?visitor_id=vis_verify_ecosystem")"
echo "$quota" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('enabled') is True, d
assert 'remaining' in d, d
print('sandbox quota remaining=%s'%d['remaining'])
" || fail "sandbox quota endpoint"
ok "hub sandbox quota"

# Stats live (monitor feed)
live="$(curl -sf "$HUB_URL/ai-market/v2/stats/live?limit=5")"
echo "$live" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('protocol_version')=='v2', d
summary=d.get('summary') or {}
assert 'open_channels' in summary, 'missing open_channels in summary'
print('stats: invocations=%s open_channels=%s'%(summary.get('total_invocations'),summary.get('open_channels')))
" || fail "stats/live"
ok "hub stats/live"

# ACEX capital pricing (Agent IPO overlay → Pulse Terminal)
pricing="$(curl -sf "$HUB_URL/api/v2/capital/pricing")"
echo "$pricing" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('protocol')=='acex', d
assert 'acex_listings_live' in d, 'missing acex_listings_live (Agent IPO overlay)'
print('capital: listings=%s acex_listings_live=%s'%(len(d.get('listings') or []), d['acex_listings_live']))
" || fail "capital pricing endpoint"
ok "acex capital pricing"

# ACEX listings catalog (Agent IPO leg)
listings="$(curl -sf "$HUB_URL/api/v2/capital/listings?limit=5")"
echo "$listings" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('protocol_version')=='v2', d
assert isinstance(d.get('listings'), list), d
print('capital: floated_listings=%s'%len(d['listings']))
" || fail "capital listings endpoint"
ok "acex capital listings"

echo ""
echo "All ecosystem checks passed."
