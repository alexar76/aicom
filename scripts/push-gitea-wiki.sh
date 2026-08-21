#!/usr/bin/env bash
# Push scripts/wiki-gitea/*.md to Gitea wiki (Superowner/aicom.wiki.git).
#
# Usage:
#   ./scripts/push-gitea-wiki.sh              # push if changed
#   ./scripts/push-gitea-wiki.sh --dry-run    # show diff, no push
#   ./scripts/push-gitea-wiki.sh --list       # list source pages
#
# Auth: git credential helper only — NEVER embed user:token in URLs.
#   ./scripts/setup-gitea-git-auth.sh
#   ~/.git-credentials or osxkeychain (macOS)
#
# Optional env:
#   GITEA_HOST=http://203.0.113.10
#   GITEA_WIKI_URL=http://203.0.113.10/Superowner/aicom.wiki.git  (no credentials)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/scripts/wiki-gitea"
WIKI_WORK="${TMPDIR:-/tmp}/aicom-wiki-push-$$"
DRY_RUN=0
LIST_ONLY=0
DEFAULT_HOST="${GITEA_HOST:-http://203.0.113.10}"

sanitize_url() {
  python3 - "$1" <<'PY'
import sys, urllib.parse
p = urllib.parse.urlsplit(sys.argv[1])
netloc = p.hostname or ""
if p.port:
    netloc = f"{netloc}:{p.port}"
print(urllib.parse.urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment)))
PY
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --list) LIST_ONLY=1 ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$SRC" ]]; then
  echo "Missing wiki sources: $SRC" >&2
  exit 1
fi

mapfile -t PAGES < <(find "$SRC" -maxdepth 1 -name '*.md' ! -name 'README.md' -printf '%f\n' | sort)
if [[ ${#PAGES[@]} -eq 0 ]]; then
  echo "No wiki pages in $SRC (expected *.md except README.md)" >&2
  exit 1
fi

echo "Wiki sources: ${#PAGES[@]} page(s) in scripts/wiki-gitea/"
if [[ "$LIST_ONLY" -eq 1 ]]; then
  printf '  - %s\n' "${PAGES[@]}"
  exit 0
fi

# Resolve clone URL (never with embedded credentials)
if [[ -z "${GITEA_WIKI_URL:-}" ]] && [[ -f "${ROOT}/.env" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "${ROOT}/.env" 2>/dev/null || true
  set -u
fi

if [[ -z "${GITEA_WIKI_URL:-}" ]]; then
  base="${DEFAULT_HOST%/}"
  GITEA_WIKI_URL="${base}/Superowner/aicom.wiki.git"
fi

GITEA_WIKI_URL="$(sanitize_url "$GITEA_WIKI_URL")"

if ! python3 - "$GITEA_WIKI_URL" <<'PY'
import sys, urllib.parse
p = urllib.parse.urlsplit(sys.argv[1])
sys.exit(0 if not (p.username or p.password) else 1)
PY
then
  echo "GITEA_WIKI_URL must not contain username/password. Run ./scripts/setup-gitea-git-auth.sh" >&2
  exit 1
fi

rm -rf "$WIKI_WORK"
git clone --quiet "$GITEA_WIKI_URL" "$WIKI_WORK"
cd "$WIKI_WORK"
git checkout master 2>/dev/null || git checkout -b master

for base in "${PAGES[@]}"; do
  cp -f "$SRC/$base" "$WIKI_WORK/"
done

for old in "$WIKI_WORK"/*.md; do
  [[ -f "$old" ]] || continue
  base="$(basename "$old")"
  [[ "$base" == "README.md" ]] && continue
  [[ -f "$SRC/$base" ]] || rm -f "$old"
done

git add -A
if git diff --staged --quiet; then
  echo "Wiki unchanged — nothing to push."
  rm -rf "$WIKI_WORK"
  exit 0
fi

echo "--- Staged changes ---"
git diff --staged --stat

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run — not pushing."
  rm -rf "$WIKI_WORK"
  exit 0
fi

git commit -m "docs(wiki): sync from scripts/wiki-gitea"
git push origin HEAD:master
git push origin HEAD:main 2>/dev/null || git push -u origin HEAD:main 2>/dev/null || true
rm -rf "$WIKI_WORK"
echo "Wiki updated (${#PAGES[@]} pages): ${GITEA_WIKI_URL}"
