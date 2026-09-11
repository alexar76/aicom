#!/usr/bin/env bash
# Quick health audit: CI status, Glama/PyPI badges, landing links.
#
# Usage:
#   ./scripts/audit_ecosystem_github.sh
#   ./scripts/audit_ecosystem_github.sh --no-network   # CI only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NO_NET=0
[[ "${1:-}" == "--no-network" ]] && NO_NET=1

REPOS=(
  aicom metis aimarket-mcp aimarket-oracle-gateway aimarket-plugins
  argus dioscuri theoros helios oracles alien-monitor aimarket-hub aimarket-agent
  aimarket-courses lottery platon acex ai-service-mesh aimarket-sdks
  aimarket-desktop pulse-terminal aimarket-widget aimarket-protocol
)

echo "=== GitHub Actions — latest run per repo ==="
FAIL_CI=0
for r in "${REPOS[@]}"; do
  if ! line=$(gh run list -R "alexar76/$r" --limit 1 --json conclusion,workflowName,createdAt 2>/dev/null); then
    echo "SKIP $r (no access or missing repo)"
    continue
  fi
  conclusion=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['conclusion'] if d else 'none')" <<< "$line")
  wf=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['workflowName'] if d else '-')" <<< "$line")
  ts=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['createdAt'][:10] if d else '-')" <<< "$line")
  if [[ "$conclusion" == "success" ]]; then
    echo "OK   $r ($wf @ $ts)"
  else
    echo "FAIL $r ($wf @ $ts) → $conclusion"
    FAIL_CI=$((FAIL_CI + 1))
  fi
done

echo ""
echo "=== Landing GitHub links ==="
if [[ "$NO_NET" -eq 0 ]]; then
  "$ROOT/scripts/verify_ecosystem_landing_links.sh" || true
else
  echo "SKIP ( --no-network )"
fi

echo ""
echo "=== Glama score badges ==="
if [[ "$NO_NET" -eq 0 ]]; then
  for slug in aimarket-oracle-gateway aimarket-mcp aimarket-plugins; do
    url="https://glama.ai/mcp/servers/alexar76/${slug}/badges/score.svg"
    code=$(curl -fsSL -o /dev/null -w '%{http_code}' --max-time 15 "$url" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then echo "OK   $url"; else echo "FAIL ($code) $url"; FAIL_CI=$((FAIL_CI + 1)); fi
  done
else
  echo "SKIP ( --no-network )"
fi

echo ""
if [[ "$FAIL_CI" -eq 0 ]]; then
  echo "Audit: all checks passed."
  exit 0
fi
echo "Audit: $FAIL_CI issue(s) — see above."
exit 1
