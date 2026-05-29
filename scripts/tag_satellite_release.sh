#!/usr/bin/env bash
# Tag satellite GitHub repos and create Releases (after publish_all_repos sync).
#
# Usage:
#   ./scripts/tag_satellite_release.sh v0.1.0 aimarket-protocol aimarket-sdks aimarket-hub
#   ./scripts/tag_satellite_release.sh --dry-run v0.1.0 aimarket-protocol
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GITHUB_ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
GITHUB_HOST="${SATELLITE_GITHUB_HOST:-github.com}"
BRANCH="${SATELLITE_BRANCH:-main}"
DRY_RUN=0
TAG=""
SAT_IDS=()

usage() {
  cat <<'EOF'
tag_satellite_release.sh — push git tag + GitHub Release on satellite repos

  ./scripts/tag_satellite_release.sh v0.1.0 aimarket-protocol aimarket-sdks aimarket-hub
  ./scripts/tag_satellite_release.sh --dry-run v0.1.0 aimarket-hub

Requires GH_PAT or GITHUB_TOKEN. Run publish_all_repos.sh first so main matches monorepo.
Release notes: scripts/release-notes/<tag-without-v>/<satellite-id>.md
EOF
}

resolve_repo() {
  python3 - "$1" <<'PY'
import sys, yaml
from pathlib import Path
sid = sys.argv[1]
m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
for s in m.get("satellites", []):
    if s["id"] == sid:
        print(s.get("repo") or sid)
        raise SystemExit(0)
print(f"unknown satellite: {sid}", file=sys.stderr)
raise SystemExit(1)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    v*) TAG="$1"; shift ;;
    *) SAT_IDS+=("$1"); shift ;;
  esac
done

[[ -n "$TAG" ]] || { usage; exit 1; }
[[ ${#SAT_IDS[@]} -gt 0 ]] || { echo "error: list satellite ids" >&2; exit 1; }

TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
[[ -n "$TOKEN" || "$DRY_RUN" -eq 1 ]] || {
  echo "error: set GH_PAT or GITHUB_TOKEN" >&2
  exit 2
}

git_auth() {
  if [[ -n "${TOKEN:-}" ]]; then
    local auth_header="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=http.extraHeader \
    GIT_CONFIG_VALUE_0="$auth_header" \
    git "$@"
  else
    git "$@"
  fi
}

notes_file() {
  local sat_id="$1"
  local ver="${TAG#v}"
  local f="$ROOT/scripts/release-notes/${ver}/${sat_id}.md"
  if [[ -f "$f" ]]; then
    echo "$f"
  else
    echo ""
  fi
}

for sat_id in "${SAT_IDS[@]}"; do
  repo="$(resolve_repo "$sat_id")"
  remote="https://${GITHUB_HOST}/${GITHUB_ORG}/${repo}.git"
  notes="$(notes_file "$sat_id")"

  echo ""
  echo "━━━ ${sat_id} → ${GITHUB_ORG}/${repo} tag ${TAG} ━━━"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would tag ${remote} @ ${BRANCH} and gh release create ${TAG}"
    continue
  fi

  work="$(mktemp -d)"
  trap 'rm -rf "$work"' RETURN

  git_auth clone --depth 1 --branch "$BRANCH" "$remote" "$work/clone"
  cd "$work/clone"

  if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "  ℹ️  Tag ${TAG} already exists locally"
  else
    git tag -a "$TAG" -m "release: ${TAG} (${sat_id})"
    echo "  ✓ Created tag ${TAG}"
  fi

  git_auth push origin "$TAG" 2>&1 || echo "  ⚠️  Tag push failed (may already exist on remote)"

  cd "$ROOT"
  export GH_TOKEN="${TOKEN:-}"
  if GH_TOKEN="${TOKEN:-}" gh release view "$TAG" --repo "${GITHUB_ORG}/${repo}" &>/dev/null; then
    echo "  ℹ️  GitHub Release ${TAG} already exists"
  elif [[ -n "$notes" ]]; then
    GH_TOKEN="${TOKEN:-}" gh release create "$TAG" --repo "${GITHUB_ORG}/${repo}" --title "${TAG}" --notes-file "$notes" \
      && echo "  ✅ GitHub Release ${TAG} created" \
      || echo "  ⚠️  Release create failed (tag ${TAG} is on remote — retry: GH_TOKEN=... gh release create ...)"
  else
    GH_TOKEN="${TOKEN:-}" gh release create "$TAG" --repo "${GITHUB_ORG}/${repo}" --title "${TAG}" --generate-notes \
      && echo "  ✅ GitHub Release ${TAG} created (auto notes)" \
      || echo "  ⚠️  Release create failed (tag pushed)"
  fi

  rm -rf "$work"
  trap - RETURN
done

echo ""
echo "Done."
