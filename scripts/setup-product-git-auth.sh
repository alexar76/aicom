#!/usr/bin/env bash
# Sanitize product git remotes under data/code/*: never embed credentials in remote URLs.
#
# - Moves any username/password from origin URL into git credential helper.
# - Rewrites origin URL to the clean https://host/org/repo.git form.
#
# Usage:
#   ./scripts/setup-product-git-auth.sh                 # fix remotes + helper
#   ./scripts/setup-product-git-auth.sh --check         # audit only (exit 1 if any URL embeds secrets)
#
# Notes:
# - Default credential store file is under the data volume so it persists in Docker:
#     data/secrets/git-credentials
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CHECK_ONLY=0
CODE_DIR="${AIFACTORY_DATA_ROOT:-$ROOT/data}/code"
CRED_FILE="${GIT_CREDENTIALS_FILE:-${AIFACTORY_DATA_ROOT:-$ROOT/data}/secrets/git-credentials}"

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

parse_url() {
  python3 - "$1" <<'PY'
import sys, urllib.parse
u = urllib.parse.urlsplit(sys.argv[1])
host = u.hostname or ""
if u.port:
    host = f"{host}:{u.port}"
print(u.scheme or "https")
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

ensure_credential_helper() {
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    git config --global --get credential.helper >/dev/null 2>&1 || {
      echo "WARN: no global credential.helper configured" >&2
    }
    return 0
  fi
  mkdir -p "$(dirname "$CRED_FILE")"
  chmod 700 "$(dirname "$CRED_FILE")" 2>/dev/null || true
  git config --global credential.helper "store --file ${CRED_FILE}"
  chmod 600 "$CRED_FILE" 2>/dev/null || true
  echo "credential.helper=store --file ${CRED_FILE}"
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

ISSUES=0
fix_one_repo() {
  local repo_dir="$1"
  cd "$repo_dir"
  if [[ ! -d .git ]]; then
    return 0
  fi
  local url
  url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ -z "$url" ]]; then
    return 0
  fi
  mapfile -t parts < <(parse_url "$url")
  local scheme="${parts[0]}" host="${parts[1]}" path="${parts[2]}" user="${parts[3]}" pass="${parts[4]}"
  local clean
  clean="$(sanitize_url "$url")"

  if [[ -n "$user" || -n "$pass" ]]; then
    ISSUES=1
    echo "REPO $(basename "$repo_dir"): credentials embedded in origin URL"
    echo "  before: $(mask_url "$url")"
    echo "  after:  $clean"
    if [[ "$CHECK_ONLY" -eq 0 ]]; then
      store_credential "$scheme" "$host" "$user" "$pass"
      git remote set-url origin "$clean"
      echo "  fixed."
    fi
  fi
}

echo "=== Product git auth setup (code_dir: $CODE_DIR) ==="
ensure_credential_helper

if [[ ! -d "$CODE_DIR" ]]; then
  echo "No code directory at: $CODE_DIR"
  exit 0
fi

for d in "$CODE_DIR"/*; do
  [[ -d "$d" ]] || continue
  fix_one_repo "$d"
done

if [[ "$CHECK_ONLY" -eq 1 && "$ISSUES" -eq 1 ]]; then
  echo ""
  echo "Run without --check to strip credentials from origin URLs and store them in the credential helper."
  exit 1
fi

echo "Done."

