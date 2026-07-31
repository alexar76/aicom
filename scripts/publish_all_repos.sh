#!/usr/bin/env bash
# =============================================================================
# publish_all_repos.sh — Idempotent push of satellite repos + trimmed aicom factory
#
# Source of truth: scripts/satellite-map.yaml
#
# NEVER use plain `git push origin` for aicom when satellites changed — that
# would upload satellite folders to alexar76/aicom. Use this script instead.
#
# Usage:
#   ./scripts/publish_all_repos.sh                    # all satellites + factory + GHCR
#   ./scripts/publish_all_repos.sh --satellites-only  # satellites only
#   ./scripts/publish_all_repos.sh --factory-only     # trimmed aicom only
#   ./scripts/publish_all_repos.sh --ghcr-only        # dispatch GHCR rebuilds only
#   ./scripts/publish_all_repos.sh --skip-ghcr        # skip container package rebuilds
#   ./scripts/publish_all_repos.sh --satellite acex   # one satellite
#   ./scripts/publish_all_repos.sh --dry-run
#   ./scripts/publish_all_repos.sh --list
#
# Environment:
#   GH_PAT / GITHUB_TOKEN       Auth for satellite pushes (+ workflow_dispatch for GHCR)
#   SATELLITE_GITHUB_ORG        Default: alexar76
#   AICOM_FACTORY_REMOTE        Factory remote (default: gh remote / GitHub aicom)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export AICOM_ROOT="$ROOT"

# Factory publish must never fall back to Gitea `origin`. Prefer explicit env,
# otherwise the local `gh` remote (git@github.com:…/aicom.git).
if [[ -z "${AICOM_FACTORY_REMOTE:-}" ]]; then
  _gh_url="$(git remote get-url gh 2>/dev/null || true)"
  if [[ "$_gh_url" == *github.com*aicom* ]]; then
    export AICOM_FACTORY_REMOTE="$_gh_url"
  fi
  unset _gh_url
fi

MODE="all"
SATELLITE=""
DRY_RUN=0
NO_PUSH=0
SKIP_GHCR=0
FACTORY_ARGS=()
MIRROR_ARGS=()
GHCR_ARGS=()

usage() {
  cat <<'EOF'
publish_all_repos.sh — push satellites to their GitHub repos + trimmed aicom factory

Modes:
  (default)           Mirror all satellites, then push trimmed factory aicom, then GHCR
  --satellites-only   Skip factory push (still dispatches GHCR unless --skip-ghcr)
  --factory-only      Push trimmed aicom only (no satellites / no GHCR)
  --ghcr-only         Only workflow_dispatch publish-ghcr.yml (GitHub Packages)
  --satellite ID      Push one satellite (see --list)

Options:
  --dry-run           Preview without network writes
  --no-push           Commit locally in temp clones only
  --skip-ghcr         Do not dispatch GHCR container rebuilds
  --list              List satellite ids from satellite-map.yaml
  -h, --help          This help

Examples:
  ./scripts/publish_all_repos.sh
  ./scripts/publish_all_repos.sh --satellite aimarket-hub
  ./scripts/publish_all_repos.sh --ghcr-only
  ./scripts/publish_all_repos.sh --factory-only --dry-run

GHCR packages (https://github.com/alexar76?tab=packages):
  Dispatched via scripts/publish_ghcr_packages.sh after a successful mirror
  for every satellite with registries: [ghcr:…] in satellite-map.yaml.

Satellite ↔ monorepo map (quick reference):
  profile (optional)   ← scripts/profile-readme/README.md → alexar76/alexar76 (manual only)
  aimarket-desktop     ← desktop-integrations/ (+ language-packs migration)
  pulse-terminal       ← apps/pulse-terminal/
  acex                 ← acex/
  ai-service-mesh      ← ai-service-mesh/
  aimarket-hub         ← aimarket-hub/
  aimarket-widget      ← aimarket-widget/
  aimarket-protocol    ← aimarket-protocol/
  aimarket-agent       ← aimarket-agent/
  aimarket-sdks        ← aimarket-sdks/
  aimarket-plugins     ← plugins/ + provenance
  aimarket-oracle-gateway ← plugins/aimarket-oracle-gateway/ (Glama MCP)
  alien-monitor        ← alien-monitor/
  oracles              ← oracles/ (17 oracles + oracle-core monorepo)
  platon               ← platon/ (UMBRAL cave app → alexar76/platon)
  lottery              ← lottery/ (AI-Agent Oracle Lottery → alexar76/lottery)
  aimarket-courses       ← courses/ → alexar76/aimarket-courses (10 courses, Colab + Pages)
  linkedin-profile-coach ← coach/ → alexar76/linked-in-profile-coach
  aicom-landing        ← aicom-landing/ → alexar76/aicom-landing
  aicom-wiki           ← scripts/wiki-gitea/ → alexar76/aicom.wiki
  argus-wiki           ← scripts/wiki-argus/ → alexar76/argus.wiki
  dioscuri             ← dioscuri/ → alexar76/dioscuri
  theoros              ← theoros/ → alexar76/theoros
  helios               ← helios/ → alexar76/helios
  metis                ← metis/ → alexar76/metis
  skopos               ← skopos/ → alexar76/skopos (landing → GitHub Pages)
  gaia                 ← gaia/ → alexar76/gaia (iot.modelmarket.dev · GHCR)

Legacy language-packs/reputation-dashboard/ is NOT a separate repo — it is
exported into aimarket-desktop at apps/reputation-dashboard/language-packs/.

Full map: scripts/satellite-map.yaml
EOF
}

list_satellites() {
  bash "$ROOT/scripts/mirror_satellites.sh" --help 2>/dev/null | head -1 || true
  python3 - <<'PY'
import yaml
from pathlib import Path
m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
org = m.get("org", "alexar76")
for s in m.get("satellites", []):
    opt = " (optional)" if s.get("optional") else ""
    paths = ", ".join(str(p) for p in (s.get("paths") or []))
    print(f"  {s['id']:22} → {org}/{s['repo']}{opt}")
    print(f"    paths: {paths}")
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --satellites-only) MODE="satellites"; shift ;;
    --factory-only)    MODE="factory"; SKIP_GHCR=1; shift ;;
    --ghcr-only)       MODE="ghcr"; shift ;;
    --skip-ghcr)       SKIP_GHCR=1; shift ;;
    --satellite)       MODE="single"; SATELLITE="${2:-}"; shift 2 ;;
    --dry-run)         DRY_RUN=1; MIRROR_ARGS+=(--dry-run); FACTORY_ARGS+=(--dry-run); GHCR_ARGS+=(--dry-run); shift ;;
    --no-push)         NO_PUSH=1; MIRROR_ARGS+=(--no-push); FACTORY_ARGS+=(--no-push); SKIP_GHCR=1; shift ;;
    --list)            list_satellites; exit 0 ;;
    -h|--help)         usage; exit 0 ;;
    -*)                echo "unknown option: $1" >&2; usage; exit 1 ;;
    *)                 MODE="single"; SATELLITE="$1"; shift ;;
  esac
done

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  publish_all_repos — satellite + factory + GHCR              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

errors=0

mirror_one_or_all() {
  if [[ -n "$SATELLITE" ]]; then
    if ((${#MIRROR_ARGS[@]})); then
      bash "$ROOT/scripts/mirror_satellites.sh" "${MIRROR_ARGS[@]}" --satellite "$SATELLITE" || return 1
    else
      bash "$ROOT/scripts/mirror_satellites.sh" --satellite "$SATELLITE" || return 1
    fi
  elif ((${#MIRROR_ARGS[@]})); then
    bash "$ROOT/scripts/mirror_satellites.sh" "${MIRROR_ARGS[@]}" || return 1
  else
    bash "$ROOT/scripts/mirror_satellites.sh" || return 1
  fi
}

push_factory() {
  if ((${#FACTORY_ARGS[@]})); then
    bash "$ROOT/scripts/publish_aicom_factory.sh" "${FACTORY_ARGS[@]}" || return 1
  else
    bash "$ROOT/scripts/publish_aicom_factory.sh" || return 1
  fi
}

dispatch_ghcr() {
  local -a args=()
  if ((${#GHCR_ARGS[@]:-0})); then
    args+=("${GHCR_ARGS[@]}")
  fi
  if [[ -n "$SATELLITE" ]]; then
    args+=(--satellite "$SATELLITE")
  fi
  if ((${#args[@]})); then
    bash "$ROOT/scripts/publish_ghcr_packages.sh" "${args[@]}" || return 1
  else
    bash "$ROOT/scripts/publish_ghcr_packages.sh" || return 1
  fi
}

case "$MODE" in
  all)
    echo "Step 1/3: mirror satellites …"
    mirror_one_or_all || errors=$((errors + 1))
    echo ""
    echo "Step 2/3: push trimmed factory aicom …"
    push_factory || errors=$((errors + 1))
    if [[ "$SKIP_GHCR" -eq 0 && "$errors" -eq 0 ]]; then
      echo ""
      echo "Step 3/3: dispatch GHCR package rebuilds …"
      dispatch_ghcr || errors=$((errors + 1))
    elif [[ "$SKIP_GHCR" -eq 1 ]]; then
      echo ""
      echo "Step 3/3: GHCR skipped (--skip-ghcr)."
    else
      echo ""
      echo "Step 3/3: GHCR skipped (earlier step failed)."
    fi
    ;;
  satellites)
    echo "Mirroring satellites only …"
    mirror_one_or_all || errors=$((errors + 1))
    if [[ "$SKIP_GHCR" -eq 0 && "$errors" -eq 0 ]]; then
      echo ""
      echo "Dispatching GHCR package rebuilds …"
      dispatch_ghcr || errors=$((errors + 1))
    fi
    ;;
  factory)
    echo "Pushing trimmed factory aicom only …"
    push_factory || errors=$((errors + 1))
    ;;
  ghcr)
    echo "Dispatching GHCR package rebuilds only …"
    dispatch_ghcr || errors=$((errors + 1))
    ;;
  single)
    [[ -n "$SATELLITE" ]] || { echo "error: --satellite ID required" >&2; exit 1; }
    if [[ "$SATELLITE" == "aicom" ]]; then
      echo "Satellite id 'aicom' → using publish_aicom_factory.sh"
      push_factory || errors=$((errors + 1))
    else
      echo "Mirroring satellite: $SATELLITE …"
      mirror_one_or_all || errors=$((errors + 1))
      if [[ "$SKIP_GHCR" -eq 0 && "$errors" -eq 0 ]]; then
        # Only dispatch if this satellite actually has a ghcr: registry.
        if bash "$ROOT/scripts/publish_ghcr_packages.sh" --list --satellite "$SATELLITE" 2>/dev/null \
            | grep -q "━━━ ${SATELLITE} "; then
          echo ""
          echo "Dispatching GHCR for ${SATELLITE} …"
          dispatch_ghcr || errors=$((errors + 1))
        fi
      fi
    fi
    ;;
esac

echo ""
echo "Syncing GitHub repo descriptions …"
if [[ "$DRY_RUN" -eq 0 && "$MODE" != "ghcr" ]]; then
  python3 "$ROOT/scripts/sync_github_repo_descriptions.py" || true
fi

echo ""
echo "Syncing GitHub repo topics …"
if [[ "$DRY_RUN" -eq 0 && "$MODE" != "ghcr" ]]; then
  python3 "$ROOT/scripts/sync_github_repo_topics.py" || true
fi

echo ""
if [[ $errors -eq 0 ]]; then
  echo "✅ publish_all_repos finished successfully (idempotent — no-op if already in sync)."
  exit 0
fi

echo "⚠️  publish_all_repos finished with $errors error(s)."
exit 1
