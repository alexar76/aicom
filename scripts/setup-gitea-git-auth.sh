#!/usr/bin/env bash
# Sanitize Gitea git remotes: no PAT/user in remote URL — credentials via git credential helper only.
#
# Usage (from repo root):
#   ./scripts/setup-gitea-git-auth.sh              # fix remotes + helper
#   ./scripts/setup-gitea-git-auth.sh --check    # audit only, exit 1 if URL embeds secrets
#
# Does NOT revoke or rotate tokens. If a token was embedded in origin URL, it is moved to
# ~/.git-credentials (Linux) / credential helper and stripped from .git/config.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CHECK_ONLY=0
CRED_FILE="${GIT_CREDENTIALS_FILE:-$HOME/.git-credentials}"
DEFAULT_GITEA_HOST="${GITEA_HOST:-http://203.0.113.10}"

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# --- helpers (Python: reliable URL parse) -----------------------------------

parse_url() {
  python3 - "$1" <<'PY'
import sys, urllib.parse
u = urllib.parse.urlsplit(sys.argv[1])
host = u.hostname or ""
if u.port:
    host = f"{host}:{u.port}"
print(u.scheme or "http")
print(host)
print(u.path or "")
print(u.username or "")
print(u.password or "")
PY
}

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

mask_url() {
  python3 - "$1" <<'PY'
import sys, urllib.parse
p = urllib.parse.urlsplit(sys.argv[1])
netloc = p.hostname or ""
if p.port:
    netloc = f"{netloc}:{p.port}"
if p.username:
    netloc = "***:***@" + netloc
print(urllib.parse.urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment)))
PY
}

store_credential() {
  local scheme="$1" host="$2" user="$3" pass="$4"
  [[ -n "$user" && -n "$pass" ]] || return 0
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "  would store credential for $user@$host (not in --check mode write)"
    return 0
  fi
  git credential approve <<EOF
protocol=${scheme}
host=${host}
username=${user}
password=${pass}
EOF
}

ensure_credential_helper() {
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    git config --global --get credential.helper >/dev/null 2>&1 || {
      echo "WARN: no global credential.helper configured" >&2
    }
    return 0
  fi
  if git config --global --get credential.helper >/dev/null 2>&1; then
    echo "credential.helper already set: $(git config --global credential.helper)"
  else
    if [[ "$(uname -s)" == "Darwin" ]]; then
      git config --global credential.helper osxkeychain
      echo "Set credential.helper=osxkeychain"
    else
      git config --global credential.helper "store --file ${CRED_FILE}"
      echo "Set credential.helper=store --file ${CRED_FILE}"
    fi
  fi
  if [[ -f "$CRED_FILE" ]]; then
    chmod 600 "$CRED_FILE" 2>/dev/null || true
  fi
}

# --- audit / fix remotes ----------------------------------------------------

ISSUES=0
fix_remote() {
  local name="$1"
  local url
  url="$(git remote get-url "$name" 2>/dev/null)" || return 0
  # `mapfile` is bash 4+ and macOS ships bash 3.2, where it is `command not found`:
  # under `set -e` this aborted before a single remote was inspected.
  local parts=()
  while IFS= read -r _p; do parts+=("$_p"); done < <(parse_url "$url")
  local scheme="${parts[0]:-}" host="${parts[1]:-}" path="${parts[2]:-}" user="${parts[3]:-}" pass="${parts[4]:-}"
  local clean
  clean="$(sanitize_url "$url")"

  if [[ -n "$user" || -n "$pass" ]]; then
    ISSUES=1
    echo "REMOTE $name: credentials embedded in URL"
    echo "  before: $(mask_url "$url")"
    echo "  after:  $clean"
    if [[ "$CHECK_ONLY" -eq 1 ]]; then
      return 0
    fi
    store_credential "$scheme" "$host" "$user" "$pass"
    git remote set-url "$name" "$clean"
    echo "  fixed."
  else
    echo "REMOTE $name: OK ($clean)"
  fi
}

echo "=== Gitea git auth setup (repo: $ROOT) ==="
ensure_credential_helper

if ! git remote >/dev/null 2>&1; then
  echo "Not a git repository." >&2
  exit 1
fi

while IFS= read -r remote; do
  [[ -n "$remote" ]] && fix_remote "$remote"
done < <(git remote)

# Optional public Gitea remote (no credentials in URL)
if [[ "$CHECK_ONLY" -eq 0 ]] && ! git remote get-url gitea >/dev/null 2>&1; then
  base="${DEFAULT_GITEA_HOST%/}"
  git remote add gitea "${base}/Superowner/aicom.git" 2>/dev/null || true
  echo "Added remote 'gitea' -> ${base}/Superowner/aicom.git (uses same credential helper)"
fi

if [[ "$CHECK_ONLY" -eq 1 && "$ISSUES" -eq 1 ]]; then
  echo ""
  echo "Run without --check to strip credentials from remote URLs and store them in the credential helper."
  exit 1
fi

if [[ "$CHECK_ONLY" -eq 0 ]]; then
  echo ""
  echo "Remotes now:"
  git remote -v | sed -E 's#(//)[^:@/]+:[^@]+@#\1***:***@#g'
  echo ""
  echo "Verify: git fetch origin   (or: git push origin main)"
  echo "Wiki push uses clean URL too: ./scripts/push-gitea-wiki.sh --dry-run"
  echo ""
  echo "Long-term: put Gitea behind HTTPS (nginx/caddy + Let's Encrypt)."
fi
