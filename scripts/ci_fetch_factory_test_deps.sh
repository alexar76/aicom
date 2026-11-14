#!/usr/bin/env bash
# Clone satellite repos excluded from the trimmed alexar76/aicom factory tree so pytest can import them.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

HUB_PROD_GATE_PATCH="$ROOT/scripts/ci_patches/aimarket-hub-cli-prod-forbidden-flags.patch"

clone_if_missing() {
  local dir="$1"
  local repo="$2"
  # Never wipe an existing tree — on the monorepo acex/ may lack pyproject.toml
  # (contracts-only) and must not be replaced by a nested GitHub clone.
  if [[ -e "$dir" ]]; then
    return 0
  fi
  git clone --depth 1 "https://github.com/alexar76/${repo}.git" "$dir"
}

# Factory CI clones alexar76/aimarket-hub. That satellite must expose
# prod_forbidden_flags_active (parity with security.prod_startup_guard) or
# tests/test_prod_startup_guard.py fails. When GitHub lags the monorepo, apply
# the factory-shipped patch (no-op once the satellite catches up).
hub_has_prod_forbidden_gate() {
  [[ -f aimarket-hub/aimarket_hub/cli.py ]] \
    && grep -q 'def prod_forbidden_flags_active' aimarket-hub/aimarket_hub/cli.py
}

ensure_hub_prod_forbidden_gate() {
  if hub_has_prod_forbidden_gate; then
    return 0
  fi
  if [[ ! -f aimarket-hub/aimarket_hub/cli.py ]]; then
    echo "ci_fetch_factory_test_deps: aimarket-hub/aimarket_hub/cli.py missing" >&2
    exit 1
  fi
  if [[ ! -f "$HUB_PROD_GATE_PATCH" ]]; then
    cat >&2 <<'EOF'
ci_fetch_factory_test_deps: aimarket-hub lacks prod_forbidden_flags_active
and scripts/ci_patches/aimarket-hub-cli-prod-forbidden-flags.patch is missing.

Publish the satellite from the monorepo:
  ./scripts/publish_all_repos.sh --satellite aimarket-hub
EOF
    exit 1
  fi
  echo "ci_fetch_factory_test_deps: patching stale aimarket-hub CLI prod gate"
  if ! patch -p1 -d aimarket-hub < "$HUB_PROD_GATE_PATCH"; then
    cat >&2 <<'EOF'
ci_fetch_factory_test_deps: failed to patch aimarket-hub CLI.

Publish a current hub satellite (preferred) or refresh the CI patch:
  ./scripts/publish_all_repos.sh --satellite aimarket-hub
EOF
    exit 1
  fi
  if ! hub_has_prod_forbidden_gate; then
    echo "ci_fetch_factory_test_deps: patch applied but gate still missing" >&2
    exit 1
  fi
}

clone_if_missing acex acex
clone_if_missing aimarket-hub aimarket-hub
# physical_capabilities / knowledge sync import atlas.products + atlas.stations
clone_if_missing atlas atlas
# Signing-identity + deployment-registry tests import these packages by path.
clone_if_missing oracles oracles
clone_if_missing platon platon
clone_if_missing alien-monitor alien-monitor
clone_if_missing argus argus
clone_if_missing metis metis
clone_if_missing treasury treasury
clone_if_missing aimarket-mcp aimarket-mcp
# Factory pytest imports / reads these satellites (trimmed out of alexar76/aicom).
clone_if_missing momus momus
clone_if_missing skopos skopos
clone_if_missing lottery lottery
clone_if_missing ai-service-mesh ai-service-mesh
clone_if_missing aimarket-agent aimarket-agent
clone_if_missing aimarket-bridges aimarket-bridges
clone_if_missing gaia gaia
clone_if_missing hephaestus hephaestus
clone_if_missing basanos basanos
clone_if_missing histor histor
clone_if_missing warden warden
clone_if_missing aimarket-protocol aimarket-protocol
clone_if_missing themis themis
clone_if_missing create-aimarket-agent create-aimarket-agent
clone_if_missing cite-desks cite-desks
clone_if_missing dioscuri dioscuri
# courses/ is published as alexar76/aimarket-courses
clone_if_missing courses aimarket-courses
ensure_hub_prod_forbidden_gate

if [[ ! -d plugins/aimarket-mcp-packager ]]; then
  tmp_plugins="_ci_aimarket-plugins"
  rm -rf "$tmp_plugins"
  git clone --depth 1 https://github.com/alexar76/aimarket-plugins.git "$tmp_plugins"
  mkdir -p plugins
  cp -R "$tmp_plugins/plugins/." plugins/
  rm -rf "$tmp_plugins"
fi

# Hub satellite ships provenance; keep an editable install path for factory tests.
if [[ ! -d plugins/aimarket-provenance && -d aimarket-hub/plugins/aimarket-provenance ]]; then
  mkdir -p plugins
  cp -R aimarket-hub/plugins/aimarket-provenance plugins/aimarket-provenance
fi
