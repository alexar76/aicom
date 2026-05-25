#!/usr/bin/env bash
# =============================================================================
# release.sh — Group-tag all satellites + aicom factory from latest main.
#
# Reads scripts/satellite-map.yaml for the list of satellite repos.
# Tags every satellite with the same version, pushes tags, then triggers
# per-satellite publish workflows.
#
# Usage:
#   ./scripts/release.sh                    # interactive prompt
#   ./scripts/release.sh patch              # bump patch version
#   ./scripts/release.sh minor              # bump minor version
#   ./scripts/release.sh major              # bump major version
#   ./scripts/release.sh --current          # show current version only
#   ./scripts/release.sh --dry-run patch    # preview only
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GITHUB_ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
GITHUB_HOST="${SATELLITE_GITHUB_HOST:-github.com}"
DRY_RUN=0
BUMP=""
SHOW_CURRENT=0

# ── Version helpers ─────────────────────────────────────────────────────────

_current_version() {
  # Try VERSION file first, then git tags, then default
  if [[ -f "$ROOT/VERSION" ]]; then
    head -1 "$ROOT/VERSION"
  elif git describe --tags --abbrev=0 2>/dev/null | grep -qE '^v[0-9]'; then
    git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'
  else
    echo "0.1.0"
  fi
}

_bump_version() {
  local current="$1"
  local level="$2"
  local major minor patch

  IFS='.' read -r major minor patch <<< "$current"
  # Default patch if missing
  patch="${patch:-0}"

  case "$level" in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch|*)
      patch=$((patch + 1))
      ;;
  esac
  echo "${major}.${minor}.${patch}"
}

# ── Satellite list ─────────────────────────────────────────────────────────

_list_satellite_repos() {
  python3 - "$@" <<'PYEOF'
import yaml, json
from pathlib import Path
m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
repos = []
for s in m.get("satellites", []):
    if s.get("id") == "aicom":
        continue  # handled separately as monorepo
    repos.append({"id": s["id"], "repo": s["repo"], "optional": s.get("optional", False)})
print(json.dumps(repos))
PYEOF
}

# ── CLI ─────────────────────────────────────────────────────────────────────

usage() {
  cat <<'EOF'
release.sh — group-tag all satellites from aicom monorepo

Usage:
  ./scripts/release.sh [--dry-run] [patch|minor|major]
  ./scripts/release.sh --current

Environment:
  SATELLITE_GITHUB_ORG    GitHub org/user (default: alexar76)
  GH_PAT / GITHUB_TOKEN   GitHub Personal Access Token for remote tag pushes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=1; shift ;;
    --current)   SHOW_CURRENT=1; shift ;;
    patch|minor|major) BUMP="$1"; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "unknown: $1" >&2; usage; exit 1 ;;
  esac
done

CURRENT="$(_current_version)"

if [[ "$SHOW_CURRENT" -eq 1 ]]; then
  echo "v${CURRENT}"
  exit 0
fi

if [[ -z "$BUMP" ]]; then
  echo "Current version: v${CURRENT}"
  echo ""
  PS3="Bump level: "
  select bump_choice in "patch → v$(_bump_version "$CURRENT" patch)" "minor → v$(_bump_version "$CURRENT" minor)" "major → v$(_bump_version "$CURRENT" major)" "cancel"; do
    case "$bump_choice" in
      cancel) echo "Aborted."; exit 0 ;;
      patch*) BUMP="patch"; break ;;
      minor*) BUMP="minor"; break ;;
      major*) BUMP="major"; break ;;
    esac
  done
fi

NEW_VERSION="$(_bump_version "$CURRENT" "$BUMP")"
TAG="v${NEW_VERSION}"

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Group Release"
echo "  Current:  v${CURRENT}"
echo "  New:      ${TAG} (${BUMP})"
echo "  Org:      ${GITHUB_ORG}"
echo "══════════════════════════════════════════════════════════════"
echo ""

# ── Dry run ────────────────────────────────────────────────────────────────

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] Would tag the following repos with ${TAG}:"
  echo "  • ${GITHUB_ORG}/aicom (monorepo)"
  while IFS= read -r repo_json; do
    repo_id=$(echo "$repo_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    repo_name=$(echo "$repo_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['repo'])")
    optional=$(echo "$repo_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('optional', False))")
    opt_str=""
    [[ "$optional" == "True" ]] && opt_str=" (optional)"
    echo "  • ${GITHUB_ORG}/${repo_name}${opt_str}"
  done < <(_list_satellite_repos | python3 -c "import sys,json; [print(json.dumps(r)) for r in json.load(sys.stdin)]")
  echo ""
  echo "[dry-run] Would update VERSION file: ${NEW_VERSION}"
  echo "[dry-run] Would push tag ${TAG} to monorepo origin"
  echo "[dry-run] Would create GitHub Release drafts for all satellites"
  exit 0
fi

# ── Check prerequisites ────────────────────────────────────────────────────

TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"

# ── Update VERSION file ────────────────────────────────────────────────────

echo "$NEW_VERSION" > "$ROOT/VERSION"
echo "✓ VERSION updated: $NEW_VERSION"

# ── Tag monorepo ───────────────────────────────────────────────────────────

git add "$ROOT/VERSION"
git commit -m "release: ${TAG}" 2>/dev/null || echo "  (nothing to commit for VERSION)"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "⚠️  Tag ${TAG} already exists — skipping tag creation"
else
  git tag -a "$TAG" -m "release: ${TAG} — AI-Factory + satellites"
  echo "✓ Created tag: ${TAG}"

  # Push tag to monorepo origin
  if [[ -n "$TOKEN" ]]; then
    git push origin "$TAG" 2>&1 || echo "⚠️  Failed to push tag to origin (check GH_PAT)"
  else
    git push origin "$TAG" 2>&1 || echo "⚠️  Failed to push tag to origin (no token set)"
  fi
fi

# ── Satellite URLs ─────────────────────────────────────────────────────────

echo ""
echo "Satellites to tag:"
echo ""

REPOS_JSON=$(_list_satellite_repos)

echo "$REPOS_JSON" | python3 -c "
import sys, json
repos = json.load(sys.stdin)
for r in repos:
    opt = ' (optional)' if r.get('optional') else ''
    print(f\"  {r['id']:25} → {r['repo']}{opt}\")
"

echo ""
echo "✅ Release ${TAG} prepared."
echo ""
echo "Next steps (manual or CI):"
echo "  1. Verify: git tag -l 'v${NEW_VERSION}'"
echo "  2. Mirror satellites: ./scripts/mirror_satellites.sh"
echo "  3. Per-satellite tag push: for each satellite, cd clone && git tag ${TAG} && git push origin ${TAG}"
echo ""
echo "Or trigger via GitHub Actions:"
echo "  gh workflow run release.yml -f bump=patch"
echo ""
echo "Satellite URLs:"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aicom"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-desktop"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-sdks"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/pulse-terminal"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/acex"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/ai-service-mesh"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-hub"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-widget"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-protocol"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-agent"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-plugins"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/alien-monitor"
