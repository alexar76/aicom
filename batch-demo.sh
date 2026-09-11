#!/usr/bin/env bash
# Enqueue several showcase ideas (same entrypoint as demo.sh). Requires a running stack + API.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEMO="${ROOT}/demo.sh"
if [[ ! -x "$DEMO" ]]; then
  chmod +x "$DEMO" || true
fi

declare -a PHRASES=(
  "Landing page for AI-powered resume builder — hero, features, pricing, waitlist."
  "Marketing site for vegan meal delivery subscription."
  "Portfolio for freelance photographer with contact funnel."
  "SaaS dashboard MVP for remote team standups."
  "Privacy-first habit tracker landing + waitlist."
)

echo "→ ${#PHRASES[@]} demo phrases — open Admin → Pipeline after each run completes."
for phrase in "${PHRASES[@]}"; do
  echo ""
  echo "=== $phrase ==="
  "$DEMO" "$phrase" || echo "(demo.sh exited non-zero — check Docker / keys)"
done

echo ""
echo "Done. Watch progress at Admin → Pipeline / Sandbox."
