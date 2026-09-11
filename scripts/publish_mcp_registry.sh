#!/usr/bin/env bash
# Validate and optionally dispatch Official MCP Registry publish workflows.
# Requires: GH_PAT (alexar76) for --dispatch; curl for mcp-publisher install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VALIDATE_ONLY=0
PUBLISH=0
DISPATCH=0
CHECK_LIVE=0
LOGIN=0
declare -a ONLY=()

usage() {
  cat <<'EOF'
Usage: publish_mcp_registry.sh [--validate-only | --publish | --dispatch | --check-live | --all]

  --validate-only   Run mcp-publisher validate on all server.json (default)
  --login           Authenticate with the registry (browser, sign in as alexar76)
  --publish         Publish server.json straight from this checkout
  --only NAME       Restrict --publish to this manifest (repeatable)
  --dispatch        workflow_dispatch publish-mcp-registry.yml on each GitHub repo
  --check-live      Query registry.modelcontextprotocol.io for alexar76 servers
  --all             validate + check-live + dispatch

THE REGISTRY DOES NOT READ GITHUB. Pushing a server.json changes nothing there; the
registry only knows what was published TO it. Verified 2026-08-16: after a push, the live
listing still advertised the old `https://{aimarket_host}/mcp` template.

Before --publish, authenticate as the namespace owner:

    mcp-publisher login github

Every name here is io.github.alexar76/*, so the browser must sign in as **alexar76**.
Namespace ownership is the entire check — signing in as another account is rejected.

Requires PyPI/npm package versions in server.json to match published artifacts.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --validate-only) VALIDATE_ONLY=1 ;;
    --login) LOGIN=1 ;;
    --publish) PUBLISH=1 ;;
    --only) shift; ONLY+=("$1") ;;
    --dispatch) DISPATCH=1 ;;
    --check-live) CHECK_LIVE=1 ;;
    --all) VALIDATE_ONLY=1; DISPATCH=1; CHECK_LIVE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [[ "$LOGIN" -eq 0 && "$VALIDATE_ONLY" -eq 0 && "$PUBLISH" -eq 0 && "$DISPATCH" -eq 0 && "$CHECK_LIVE" -eq 0 ]]; then
  VALIDATE_ONLY=1
fi

declare -a MANIFESTS=(
  # The hosted endpoint comes first because it is the only entry a reader can try without
  # installing anything — every other listing here asks them to clone or pip install first.
  "aimarket-hub|aimarket-hub/server.json"
  "aimarket-mcp|aimarket-mcp/server.json"
  "aimarket-oracle-gateway|plugins/aimarket-oracle-gateway/server.json"
  "aimarket-plugins|plugins/aimarket-mcp-packager/server.json"
  "argus|argus/server.json"
  "warden|warden/server.json"
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

if [[ "$LOGIN" -eq 1 ]]; then
  ensure_publisher
  echo "=== mcp-publisher login github ==="
  echo "    Sign in as alexar76. Every name here is io.github.alexar76/*, and namespace"
  echo "    ownership is the entire check — another account is rejected."
  "$PUBLISHER" login github
fi

if [[ "$PUBLISH" -eq 1 ]]; then
  ensure_publisher
  echo "=== mcp-publisher publish ==="
  echo "    (a push to GitHub does not do this — the registry only knows what is sent to it)"
  failed=0
  for entry in "${MANIFESTS[@]}"; do
    repo="${entry%%|*}"
    path="${entry#*|}"
    if [[ ! -f "$path" ]]; then
      echo "  ✗ $repo — missing $path" >&2
      exit 1
    fi
    if (( ${#ONLY[@]} )) && ! printf '%s\n' "${ONLY[@]}" | grep -qx "$repo"; then
      continue
    fi
    # A manifest that declares an older version than the artifact actually on PyPI/npm
    # would list a release nobody can install. Three of these were behind their packages
    # on 2026-08-16, so publishing the whole set unfiltered was a way to ship stale
    # listings by accident.
    if ! drift="$(python3 "$ROOT/scripts/check_manifest_version.py" "$path" 2>&1)"; then
      echo "  ✗ $repo — $drift" >&2
      echo "    bump the manifest to match, or publish only what you mean:" >&2
      echo "    $0 --publish --only aimarket-hub --only aimarket-mcp" >&2
      failed=1
      continue
    fi
    echo "  → $repo ($path) $drift"
    if ! "$PUBLISHER" publish "$path"; then
      failed=1
      echo "  ✗ $repo failed. If that was an auth error: mcp-publisher login github," >&2
      echo "    signing in as alexar76 — every name here is io.github.alexar76/*." >&2
    fi
  done
  if (( failed )); then
    echo "  ✗ some manifests were not published" >&2
    exit 1
  fi
  echo "  ✓ published — confirm with: $0 --check-live"
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
