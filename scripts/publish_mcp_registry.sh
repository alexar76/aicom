#!/usr/bin/env bash
# Validate and optionally dispatch Official MCP Registry publish workflows.
# Requires: GH_PAT (alexar76) for --dispatch; curl for mcp-publisher install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VALIDATE_ONLY=0
DISPATCH=0
CHECK_LIVE=0

usage() {
  cat <<'EOF'
Usage: publish_mcp_registry.sh [--validate-only | --dispatch | --check-live | --all]

  --validate-only   Run mcp-publisher validate on all server.json (default)
  --dispatch        workflow_dispatch publish-mcp-registry.yml on each GitHub repo
  --check-live      Query registry.modelcontextprotocol.io for alexar76 servers
  --all             validate + check-live + dispatch

Requires PyPI/npm package versions in server.json to match published artifacts before --dispatch.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --validate-only) VALIDATE_ONLY=1 ;;
    --dispatch) DISPATCH=1 ;;
    --check-live) CHECK_LIVE=1 ;;
    --all) VALIDATE_ONLY=1; DISPATCH=1; CHECK_LIVE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [[ "$VALIDATE_ONLY" -eq 0 && "$DISPATCH" -eq 0 && "$CHECK_LIVE" -eq 0 ]]; then
  VALIDATE_ONLY=1
fi

declare -a MANIFESTS=(
  "aimarket-mcp|aimarket-mcp/server.json"
  "aimarket-oracle-gateway|plugins/aimarket-oracle-gateway/server.json"
  "aimarket-plugins|plugins/aimarket-mcp-packager/server.json"
  "argus|argus/server.json"
)

ensure_publisher() {
  if command -v mcp-publisher >/dev/null 2>&1; then
    PUBLISHER=mcp-publisher
    return
  fi
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL \
    "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
    | tar xz -C "$tmp" mcp-publisher
  PUBLISHER="$tmp/mcp-publisher"
  chmod +x "$PUBLISHER"
  echo "Using downloaded mcp-publisher from $tmp"
}

if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
  ensure_publisher
  echo "=== mcp-publisher validate ==="
  for entry in "${MANIFESTS[@]}"; do
    repo="${entry%%|*}"
    path="${entry#*|}"
    if [[ ! -f "$path" ]]; then
      echo "  ✗ $repo — missing $path" >&2
      exit 1
    fi
    echo "  → $repo ($path)"
    "$PUBLISHER" validate "$path"
  done
  echo "  ✓ all server.json valid"
fi

if [[ "$CHECK_LIVE" -eq 1 ]]; then
  echo "=== registry.modelcontextprotocol.io (alexar76) ==="
  curl -fsSL "https://registry.modelcontextprotocol.io/v0.1/servers?search=alexar76" \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('servers', []):
    s = item.get('server', {})
    o = item.get('_meta', {}).get('io.modelcontextprotocol.registry/official', {})
    print(f\"  {s.get('name')} v{s.get('version')} [{o.get('status')}]\")
if not data.get('servers'):
    print('  (no servers found)')
"
fi

if [[ "$DISPATCH" -eq 1 ]]; then
  echo "=== dispatch publish-mcp-registry.yml (alexar76) ==="
  for entry in "${MANIFESTS[@]}"; do
    repo="${entry%%|*}"
    if [[ "$repo" == "aimarket-oracle-gateway" ]]; then
      gh_repo="aimarket-oracle-gateway"
    elif [[ "$repo" == "aimarket-plugins" ]]; then
      gh_repo="aimarket-plugins"
    else
      gh_repo="$repo"
    fi
    python3 "$ROOT/scripts/dispatch_github_workflow.py" "$gh_repo" publish-mcp-registry.yml main \
      || echo "  ⚠️  dispatch failed for $gh_repo (check GH_PAT / workflow exists)" >&2
  done
fi
