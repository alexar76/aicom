#!/bin/bash
# Test order for the Multica provider, second design (2026-11-05). Runs on attested as root.
# The buyer key stays inside the daemon container's environment; nothing secret is printed.
set -u
if [ "${SKIP_WAIT:-0}" != 1 ]; then
reset=$(docker exec multica-provider python -c "
import urllib.request, json
r = urllib.request.urlopen(urllib.request.Request('https://api.github.com/rate_limit', headers={'User-Agent': 'aicom-multica-provider'}), timeout=10)
print(json.load(r)['resources']['core']['reset'])")
wait=$((reset + 1 - $(date +%s)))
echo "$(date -u +%T) waiting ${wait}s for GitHub's reset"
# Who spends the host's unauthenticated limit: every container's network namespace (and the host's) sampled for
# connections to GitHub's API addresses from 3 s before the reset to 30 s after it.
IPS='140\.82\.(11[2-9]|12[0-7])\.[0-9]+'  # GitHub's 140.82.112.0/20, where api.github.com lives
declare -A NAME
for c in $(docker ps -q); do NAME[$(docker inspect -f '{{.State.Pid}}' "$c")]=$(docker inspect -f '{{.Name}}' "$c" | tr -d /); done
capture() {
  local end=$((SECONDS + 33))
  while [ $SECONDS -lt $end ]; do
    for pid in "${!NAME[@]}"; do nsenter -t "$pid" -n ss -tnH 2>/dev/null | grep -E "($IPS):443" | awk -v n="${NAME[$pid]}" '{print n, $5}'; done
    ss -tnpH 2>/dev/null | grep -E "($IPS):443" | awk '{print "HOST", $5, $6}'
    sleep 0.3
  done | sort | uniq -c | sort -rn | head -15 > /root/multica-provider-20261104/github-consumers.txt
}
[ "$wait" -gt 3 ] && sleep $((wait - 3))
capture &
CAP=$!
sleep 3
else
  echo "$(date -u +%T) no wait (GITHUB_TOKEN set)"; CAP=""
  echo "(no capture in this run)" > /root/multica-provider-20261104/github-consumers.txt
fi
hub() {  # $1 = JSON body; prints HTTP code then the body
  docker exec -i -u node multica-daemon sh -c 'curl -sS -o /tmp/r.json -w "%{http_code}\n" -X POST -H "X-API-Key: $AIMARKET_API_KEY" -H "content-type: application/json" --data-binary @- https://hub.attestedmemory.net/ai-market/v2/invoke; cat /tmp/r.json; rm -f /tmp/r.json' <<<"$1"
}
out=$(hub "{\"product_id\":\"github-digest-order\",\"capability_id\":\"github.digest.order@v1\",\"source_hub\":\"local\",\"input\":{\"login\":\"${LOGIN:-octocat}\",\"days\":${DAYS:-7}},\"max_price_usd\":0.05}")
code=$(head -1 <<<"$out")
echo "$(date -u +%T) order HTTP $code"
python3 -c "
import json, sys
b = json.loads(sys.stdin.read().split('\n', 1)[1])
print(json.dumps({k: b.get(k) for k in ('success', 'result', 'price_usd', 'remaining_balance', 'detail')}, ensure_ascii=False)[:700])
r = b.get('receipt') or {}
print('receipt', r.get('nonce'), 'signed', bool((r.get('signature') or {}).get('value')))
" <<<"$out"
[ "$code" = 200 ] || { wait $CAP 2>/dev/null; echo "connections to api.github.com around the reset:"; cat /root/multica-provider-20261104/github-consumers.txt; exit 0; }
job=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read().split('\n',1)[1])['result']['job_id'])" <<<"$out")
for i in $(seq 1 45); do
  # The agent cannot change task status (its OpenCode rules allow reading only), so wait for its answer instead.
  st=$(docker exec -u node multica-daemon multica issue search "$job" --include-closed --output json 2>/dev/null | python3 -c "
import json, sys
issues = json.load(sys.stdin).get('issues') or []
print(issues[0]['identifier'] if issues else '')")
  n=0
  [ -n "$st" ] && n=$(docker exec -u node multica-daemon multica issue comment list "$st" --output json 2>/dev/null | python3 -c "import json,sys; print(sum(1 for c in json.load(sys.stdin) if c.get('author_type') == 'agent'))")
  echo "$(date -u +%T) task ${st:-not-yet} agent answers $n"
  [ "${n:-0}" -gt 0 ] && break
  sleep 15
done
sleep 5
read_out=$(hub "{\"product_id\":\"github-digest-result\",\"capability_id\":\"github.digest.result@v1\",\"source_hub\":\"local\",\"input\":{\"job_id\":\"$job\"}}")
echo "$(date -u +%T) result HTTP $(head -1 <<<"$read_out")"
python3 -c "
import json, sys
b = json.loads(sys.stdin.read().split('\n', 1)[1]); r = b.get('result') or {}
d = r.get('digest') or {}
print('status', r.get('status'), 'summary_by', r.get('summary_by'), 'items', len(d.get('items') or []), 'repos', len(d.get('repos') or []), 'events', d.get('events_in_window'))
print('summary:', d.get('summary'))
print('price', b.get('price_usd'))
" <<<"$read_out"
wait $CAP 2>/dev/null; echo "connections to api.github.com around the reset (samples, container, peer):"; cat /root/multica-provider-20261104/github-consumers.txt
anon=$(docker exec -u node multica-daemon sh -c "curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' --data '{\"product_id\":\"github-digest-result\",\"capability_id\":\"github.digest.result@v1\",\"source_hub\":\"local\",\"input\":{\"job_id\":\"$job\"}}' https://hub.attestedmemory.net/ai-market/v2/invoke")
echo "read without a buyer key: HTTP $anon"
docker exec -u node multica-daemon sh -c 'curl -sS -H "X-API-Key: $AIMARKET_API_KEY" https://hub.attestedmemory.net/ai-market/v2/account' | python3 -c "import json,sys; a=json.load(sys.stdin); print('balance', a.get('balance_usd'), 'spent', a.get('spent_usd'))"
curl -fsS http://127.0.0.1:9084/ai-market/v2/stats/live | python3 -c "import json,sys; s=json.load(sys.stdin)['summary']; print({k: s[k] for k in ('total_invocations', 'operator_self_invocations', 'external_invocations')})"
