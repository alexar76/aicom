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
#   ./scripts/publish_all_repos.sh                    # all satellites + factory
#   ./scripts/publish_all_repos.sh --satellites-only  # satellites only
#   ./scripts/publish_all_repos.sh --factory-only     # trimmed aicom only
#   ./scripts/publish_all_repos.sh --satellite acex   # one satellite
#   ./scripts/publish_all_repos.sh --dry-run
#   ./scripts/publish_all_repos.sh --list
#
# Environment:
#   GH_PAT / GITHUB_TOKEN       Auth for satellite pushes
#   SATELLITE_GITHUB_ORG        Default: alexar76
#   AICOM_FACTORY_REMOTE        Factory remote (default: git origin)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="all"
SATELLITE=""
DRY_RUN=0
NO_PUSH=0
FACTORY_ARGS=()
MIRROR_ARGS=()

usage() {
  cat <<'EOF'
publish_all_repos.sh — push satellites to their GitHub repos + trimmed aicom factory

Modes:
  (default)           Mirror all satellites, then push trimmed factory aicom
  --satellites-only   Skip factory push
  --factory-only      Push trimmed aicom only (no satellites)
  --satellite ID      Push one satellite (see --list)

Options:
  --dry-run           Preview without network writes
  --no-push           Commit locally in temp clones only
  --list              List satellite ids from satellite-map.yaml
  -h, --help          This help

Examples:
  ./scripts/publish_all_repos.sh
  ./scripts/publish_all_repos.sh --satellite aimarket-hub
  ./scripts/publish_all_repos.sh --satellite aicom-wiki
  ./scripts/publish_all_repos.sh --factory-only --dry-run

Satellite ↔ monorepo map (quick reference):
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
  aicom-wiki           ← scripts/wiki-gitea/ → alexar76/aicom.wiki

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
    --factory-only)    MODE="factory"; shift ;;
    --satellite)       MODE="single"; SATELLITE="${2:-}"; shift 2 ;;
    --dry-run)         DRY_RUN=1; MIRROR_ARGS+=(--dry-run); FACTORY_ARGS+=(--dry-run); shift ;;
    --no-push)         NO_PUSH=1; MIRROR_ARGS+=(--no-push); FACTORY_ARGS+=(--no-push); shift ;;
    --list)            list_satellites; exit 0 ;;
    -h|--help)         usage; exit 0 ;;
    -*)                echo "unknown option: $1" >&2; usage; exit 1 ;;
    *)                 MODE="single"; SATELLITE="$1"; shift ;;
  esac
done

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  publish_all_repos — satellite + factory publish             ║"
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

case "$MODE" in
  all)
    echo "Step 1/2: mirror satellites …"
    mirror_one_or_all || errors=$((errors + 1))
    echo ""
    echo "Step 2/2: push trimmed factory aicom …"
    push_factory || errors=$((errors + 1))
    ;;
  satellites)
    echo "Mirroring satellites only …"
    mirror_one_or_all || errors=$((errors + 1))
    ;;
  factory)
    echo "Pushing trimmed factory aicom only …"
    push_factory || errors=$((errors + 1))
    ;;
  single)
    [[ -n "$SATELLITE" ]] || { echo "error: --satellite ID required" >&2; exit 1; }
    if [[ "$SATELLITE" == "aicom" ]]; then
      echo "Satellite id 'aicom' → using publish_aicom_factory.sh"
      push_factory || errors=$((errors + 1))
    else
      echo "Mirroring satellite: $SATELLITE …"
      mirror_one_or_all || errors=$((errors + 1))
    fi
    ;;
esac

echo ""
echo "Syncing GitHub repo descriptions …"
if [[ "$DRY_RUN" -eq 0 ]]; then
  python3 "$ROOT/scripts/sync_github_repo_descriptions.py" || true
fi

echo ""
if [[ $errors -eq 0 ]]; then
  echo "✅ publish_all_repos finished successfully (idempotent — no-op if already in sync)."
  exit 0
fi

echo "⚠️  publish_all_repos finished with $errors error(s)."
exit 1
