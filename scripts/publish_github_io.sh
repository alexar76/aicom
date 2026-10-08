#!/usr/bin/env bash
# Publish scripts/github-io/ → alexar76/alexar76.github.io (user GitHub Pages root).
#
#   GH_PAT=... ./scripts/publish_github_io.sh
#
# The same secret scan as the satellite mirrors runs on the tree before anything is
# committed, and the token reaches git through a credential helper, never the URL
# (a URL token is written into .git/config and echoed in git's errors).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${GITHUB_IO_SOURCE:-$ROOT/scripts/github-io}"
ORG="${GITHUB_ORG:-alexar76}"
REPO="${GITHUB_IO_REPO:-alexar76.github.io}"
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
HOST="${GITHUB_HOST:-github.com}"
REMOTE="${GITHUB_IO_REMOTE:-https://${HOST}/${ORG}/${REPO}.git}"

case "$REMOTE" in
  */alexar76.github.io.git) ;;
  *) echo "error: remote must be alexar76.github.io (got: $REMOTE)" >&2; exit 2 ;;
esac

[[ -f "$SRC/index.html" ]] || { echo "missing $SRC/index.html" >&2; exit 2; }

ON_GITHUB=0
[[ "$REMOTE" == https://* ]] && ON_GITHUB=1
if [[ "$ON_GITHUB" -eq 1 ]]; then
  [[ -n "$TOKEN" ]] || { echo "set GH_PAT or GITHUB_TOKEN" >&2; exit 3; }
  export GH_TOKEN="$TOKEN"
fi

echo "━━━ ${ORG}/${REPO} (user GitHub Pages) ━━━"

# Ensure repo exists (idempotent)
if [[ "$ON_GITHUB" -eq 1 ]] && ! gh api "repos/${ORG}/${REPO}" >/dev/null 2>&1; then
  echo "Creating public repo ${ORG}/${REPO} …"
  gh api --method POST user/repos \
    -f name="$REPO" \
    -f description="AICOM ecosystem hub — redirects to modeldev.modelmarket.dev" \
    -F private=false \
    -F auto_init=false \
    -F has_issues=false \
    -F has_projects=false \
    -F has_wiki=false >/dev/null
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/github-io.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

# The helper reads the token from the environment when git asks for it.
export GITHUB_IO_TOKEN="$TOKEN"
git_auth() {
  git -c credential.helper= \
    -c credential.helper='!f() { echo "username=x-access-token"; echo "password=$GITHUB_IO_TOKEN"; }; f' "$@"
}

git_auth clone --depth 1 "$REMOTE" "$WORKDIR/repo" 2>/dev/null \
  || {
    mkdir -p "$WORKDIR/repo"
    git -C "$WORKDIR/repo" init -b main
    git -C "$WORKDIR/repo" remote add origin "$REMOTE"
  }

rsync -a --delete \
  --exclude '.git' \
  --exclude '.DS_Store' \
  "$SRC/" "$WORKDIR/repo/"

if ! bash "$ROOT/scripts/verify_mirror_secrets.sh" "$WORKDIR/repo"; then
  echo "error: ${REPO} failed the secret scan — nothing committed or pushed" >&2
  exit 1
fi

cd "$WORKDIR/repo"
git add -A
if git diff --cached --quiet; then
  echo "  ✓ already in sync"
else
  git -c user.name="alexar76" -c user.email="alexar76@users.noreply.github.com" \
    commit -m "chore: sync user Pages hub from monorepo scripts/github-io"
  git_auth push -u origin HEAD:main
  echo "  ✓ pushed main"
fi

[[ "$ON_GITHUB" -eq 1 ]] || exit 0

# Enable legacy Pages from / on main (user site)
python3 "$ROOT/scripts/ensure_github_pages.py" "$ORG" "$REPO" --legacy || true

# Touch a trivial rebuild if workflow-based later; for legacy, push is enough
echo "Live: https://${ORG}.github.io/"
