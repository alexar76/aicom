#!/usr/bin/env bash
# Publish scripts/github-io/ → alexar76/alexar76.github.io (user GitHub Pages root).
#
#   GH_PAT=... ./scripts/publish_github_io.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/github-io"
ORG="${GITHUB_ORG:-alexar76}"
REPO="${GITHUB_IO_REPO:-alexar76.github.io}"
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
HOST="${GITHUB_HOST:-github.com}"

[[ -f "$SRC/index.html" ]] || { echo "missing $SRC/index.html" >&2; exit 2; }
[[ -n "$TOKEN" ]] || { echo "set GH_PAT or GITHUB_TOKEN" >&2; exit 3; }

export GH_TOKEN="$TOKEN"
API="https://api.github.com"

echo "━━━ ${ORG}/${REPO} (user GitHub Pages) ━━━"

# Ensure repo exists (idempotent)
if ! gh api "repos/${ORG}/${REPO}" -H "Authorization: Bearer ${TOKEN}" >/dev/null 2>&1; then
  echo "Creating public repo ${ORG}/${REPO} …"
  gh api --method POST user/repos \
    -H "Authorization: Bearer ${TOKEN}" \
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

git clone --depth 1 "https://x-access-token:${TOKEN}@${HOST}/${ORG}/${REPO}.git" "$WORKDIR/repo" 2>/dev/null \
  || {
    mkdir -p "$WORKDIR/repo"
    git -C "$WORKDIR/repo" init -b main
    git -C "$WORKDIR/repo" remote add origin "https://x-access-token:${TOKEN}@${HOST}/${ORG}/${REPO}.git"
  }

rsync -a --delete \
  --exclude '.git' \
  --exclude '.DS_Store' \
  "$SRC/" "$WORKDIR/repo/"

cd "$WORKDIR/repo"
git add -A
if git diff --cached --quiet; then
  echo "  ✓ already in sync"
else
  git -c user.name="alexar76" -c user.email="alexar76@users.noreply.github.com" \
    commit -m "chore: sync user Pages hub from monorepo scripts/github-io"
  git push -u origin HEAD:main
  echo "  ✓ pushed main"
fi

# Enable legacy Pages from / on main (user site)
python3 "$ROOT/scripts/ensure_github_pages.py" "$ORG" "$REPO" --legacy || true

# Touch a trivial rebuild if workflow-based later; for legacy, push is enough
echo "Live: https://${ORG}.github.io/"
