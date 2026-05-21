#!/usr/bin/env bash
# Push scripts/wiki-gitea/*.md to Gitea wiki (Superowner/aicom.wiki.git).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/scripts/wiki-gitea"
WIKI_WORK="${TMPDIR:-/tmp}/aicom-wiki-push-$$"

if [[ ! -d "$SRC" ]] || [[ -z "$(ls -A "$SRC"/*.md 2>/dev/null)" ]]; then
  echo "No wiki sources in $SRC" >&2
  exit 1
fi

# Credentials: git credential or GITEA_WIKI_URL
if [[ -z "${GITEA_WIKI_URL:-}" ]]; then
  if [[ -f /root/.git-credentials ]]; then
    LINE="$(grep -m1 '5.129.212.122' /root/.git-credentials || grep -m1 'localhost' /root/.git-credentials)"
    GITEA_WIKI_URL="${LINE%/}/Superowner/aicom.wiki.git"
  else
    echo "Set GITEA_WIKI_URL=http://user:token@host/Superowner/aicom.wiki.git" >&2
    exit 1
  fi
fi

rm -rf "$WIKI_WORK"
git clone "$GITEA_WIKI_URL" "$WIKI_WORK"
cd "$WIKI_WORK"
git checkout master 2>/dev/null || git checkout -b master
# Sync only markdown pages (never touch .git)
find "$SRC" -maxdepth 1 -name '*.md' ! -name 'README.md' -print0 | while IFS= read -r -d '' f; do
  cp -f "$f" "$WIKI_WORK/"
done
# Remove wiki pages dropped from sources
for old in "$WIKI_WORK"/*.md; do
  base="$(basename "$old")"
  [[ "$base" == "README.md" ]] && continue
  [[ -f "$SRC/$base" ]] || rm -f "$old"
done
git add -A
if git diff --staged --quiet; then
  echo "Wiki unchanged — nothing to push."
  exit 0
fi
git commit -m "docs(wiki): sync from scripts/wiki-gitea"
# Gitea wiki UI reads branch `master`; keep main in sync too.
git push origin HEAD:master
git push origin HEAD:main 2>/dev/null || git push -u origin HEAD:main
echo "Wiki updated: $(echo "$GITEA_WIKI_URL" | sed -E 's#//[^@]+@#//#')"
