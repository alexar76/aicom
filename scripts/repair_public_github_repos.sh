#!/usr/bin/env bash
# Restore public GitHub repos after mistaken factory/satellite rsync from monorepo.
#
# - alexar76/aicom: run publish_aicom_factory.sh (strips .cursor, .github, coach tree)
# - alexar76/aicom-landing: reset to last pre-sync commit (removes .claude junk)
# - alexar76/linked-in-profile-coach: reset to last real app commit (before monorepo dump)
#
# Usage:
#   ./scripts/repair_public_github_repos.sh --dry-run
#   ./scripts/repair_public_github_repos.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=0
GIT_CRED="${GIT_CRED:-store --file ${HOME}/.git-credentials}"

LANDING_GOOD="${LANDING_GOOD_SHA:-ea13c6f}"
COACH_GOOD="${COACH_GOOD_SHA:-d5e046a}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 1 ;;
  esac
done

git_auth() {
  git -c "credential.helper=$GIT_CRED" "$@"
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

echo "=== 1/3 Factory aicom (publish_aicom_factory.sh) ==="
if [[ "$DRY_RUN" -eq 1 ]]; then
  AICOM_FACTORY_REMOTE='https://github.com/alexar76/aicom.git' "$ROOT/scripts/publish_aicom_factory.sh" --dry-run
else
  AICOM_FACTORY_REMOTE='https://github.com/alexar76/aicom.git' "$ROOT/scripts/publish_aicom_factory.sh" || {
    echo "WARN: factory publish to GitHub failed (check alexar76 PAT in ~/.git-credentials)" >&2
  }
fi

echo ""
echo "=== 2/3 aicom-landing → reset $LANDING_GOOD ==="
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
git_auth clone --depth 50 https://github.com/alexar76/aicom-landing.git "$WORKDIR/landing"
(
  cd "$WORKDIR/landing"
  run git checkout "$LANDING_GOOD"
  run git push origin "HEAD:main" --force-with-lease
)
echo "OK landing"

echo ""
echo "=== 3/3 linked-in-profile-coach → reset $COACH_GOOD ==="
git_auth clone --depth 50 https://github.com/alexar76/linked-in-profile-coach.git "$WORKDIR/coach"
(
  cd "$WORKDIR/coach"
  run git checkout "$COACH_GOOD"
  run git push origin "HEAD:main" --force-with-lease
)
echo "OK coach"

echo ""
echo "Done. Verify on GitHub:"
echo "  https://github.com/alexar76/aicom"
echo "  https://github.com/alexar76/aicom-landing"
echo "  https://github.com/alexar76/linked-in-profile-coach"
