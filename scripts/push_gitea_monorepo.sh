#!/usr/bin/env bash
# push_gitea_monorepo.sh — push the aicom monorepo to both Gitea servers IN ORDER:
#   1) Gitea#1  Superowner/aicom  (5.129.212.122) — primary
#   2) Gitea#2  alexar76/aicom    (78.17.126.214)  — mirror
#
# Auth: git credential helper (osxkeychain) or GITEA_TOKEN (same as mirror_to_gitea.sh).
# If Gitea#1 push fails locally (no Superowner creds), set GITEA_FACTORY_HOST to relay
# through the factory VPS which already has git-credentials for both hosts.
#
# Usage:
#   ./scripts/push_gitea_monorepo.sh              # push current branch (default main)
#   ./scripts/push_gitea_monorepo.sh --dry-run    # show remotes + pending commits
#   GITEA_FACTORY_HOST=root@5.129.212.122 ./scripts/push_gitea_monorepo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GITEA_BRANCH:-main}"
DRY_RUN=0
GITEA1_URL="http://5.129.212.122/Superowner/aicom.git"
GITEA2_URL="http://78.17.126.214:3000/alexar76/aicom.git"
FACTORY_HOST="${GITEA_FACTORY_HOST:-root@5.129.212.122}"
FACTORY_CRED="${GITEA_FACTORY_CRED:-/root/claudecode/aicom/data/secrets/git-credentials}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --branch)  BRANCH="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

current_branch="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "$current_branch" && "$current_branch" != "$BRANCH" ]]; then
  echo "warning: on branch '$current_branch', pushing ref '$BRANCH'" >&2
fi

git_t() {
  if [[ -n "${GITEA_TOKEN:-}" ]]; then
    git -c http.extraHeader="Authorization: token ${GITEA_TOKEN}" "$@"
  else
    git "$@"
  fi
}

# SAFETY: this pushes the FULL monorepo (complete history + all satellites) to
# Gitea. It must NEVER go to GitHub — the public GitHub mirror is the trimmed,
# single-commit publish_aicom_factory.sh snapshot. Pushing the full tree/history
# to GitHub would leak satellites and anything ever committed.
_assert_gitea_target() {
  case "$1" in
    *github.com*)
      echo "ERROR: refusing to push — '$1' looks like GitHub, not Gitea." >&2
      echo "  The full monorepo goes to Gitea only; GitHub gets the trimmed snapshot" >&2
      echo "  via publish_aicom_factory.sh. Aborting." >&2
      exit 1
      ;;
  esac
}

_remote_head() {
  local url="$1"
  git_t ls-remote "$url" "refs/heads/${BRANCH}" 2>/dev/null | awk '{print $1; exit}'
}

_local_head() {
  git rev-parse "$BRANCH"
}

_push_direct() {
  local label="$1" url="$2"
  _assert_gitea_target "$url"
  echo ""
  echo "━━━ ${label}: ${url} ━━━"
  local remote local_head
  remote="$(_remote_head "$url" || true)"
  local_head="$(_local_head)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  local  ${local_head}"
    echo "  remote ${remote:-<unreachable>}"
    if [[ -n "$remote" && "$remote" == "$local_head" ]]; then
      echo "  · up to date"
    elif [[ -n "$remote" ]]; then
      git log --oneline "${remote}..${local_head}" | sed 's/^/  + /' | head -20
    fi
    return 0
  fi
  if [[ -n "$remote" && "$remote" == "$local_head" ]]; then
    echo "  · up to date"
    return 0
  fi
  git_t push "$url" "${BRANCH}:${BRANCH}"
  remote="$(_remote_head "$url" || true)"
  if [[ "$remote" != "$local_head" ]]; then
    echo "  ✗ push reported OK but remote still at ${remote:-<unknown>}" >&2
    return 1
  fi
  echo "  ✓ pushed → ${label}"
}

_push_via_factory() {
  local label="$1" url="$2"
  _assert_gitea_target "$url"
  local remote local_head bundle
  remote="$(_remote_head "$url" || true)"
  local_head="$(_local_head)"
  if [[ -n "$remote" && "$remote" == "$local_head" ]]; then
    echo "  · up to date (factory relay skipped)"
    return 0
  fi
  echo "  ↪ relaying ${label} via ${FACTORY_HOST} (local creds missing)"
  bundle="$(mktemp /tmp/aicom-gitea-push.XXXXXX).bundle"
  # Use ${bundle-} so set -u does not abort when RETURN fires after locals unwind.
  trap 'rm -f "${bundle-}"' RETURN
  if [[ -n "$remote" ]]; then
    git bundle create "$bundle" "${remote}..${BRANCH}"
  else
    # Cannot read remote locally — ask factory (authoritative for Gitea#1 creds).
    remote="$(ssh -o BatchMode=yes "$FACTORY_HOST" bash -s "$url" "$BRANCH" "$FACTORY_CRED" <<'EOF' || true
set -euo pipefail
URL="$1"
BRANCH="$2"
CRED="$3"
git -c credential.helper="store --file ${CRED}" ls-remote "${URL}" "refs/heads/${BRANCH}" | awk '{print $1; exit}'
EOF
)" || true
    if [[ -n "$remote" && "$remote" == "$local_head" ]]; then
      echo "  · up to date (factory ls-remote)"
      rm -f "$bundle"
      trap - RETURN
      return 0
    fi
    if [[ -n "$remote" ]]; then
      git bundle create "$bundle" "${remote}..${BRANCH}"
    else
      git bundle create "$bundle" "${BRANCH}"
    fi
  fi
  scp -q "$bundle" "${FACTORY_HOST}:/tmp/aicom-push.bundle"
  ssh -o BatchMode=yes "$FACTORY_HOST" bash -s "$url" "$BRANCH" "$FACTORY_CRED" <<'EOF'
set -euo pipefail
URL="$1"
BRANCH="$2"
CRED="$3"
TMP=$(mktemp -d)
git -c credential.helper="store --file ${CRED}" clone --bare "$URL" "$TMP/repo.git"
cd "$TMP/repo.git"
BUNDLE_HEAD=$(git bundle list-heads /tmp/aicom-push.bundle | awk '{print $1; exit}')
git fetch /tmp/aicom-push.bundle "${BUNDLE_HEAD}:refs/heads/${BRANCH}"
git -c credential.helper="store --file ${CRED}" push origin "refs/heads/${BRANCH}:refs/heads/${BRANCH}"
git rev-parse "refs/heads/${BRANCH}"
rm -rf "$TMP" /tmp/aicom-push.bundle
EOF
  rm -f "$bundle"
  trap - RETURN
  echo "  ✓ pushed → ${label} (via factory)"
}

_push_one() {
  local label="$1" url="$2" allow_factory="${3:-0}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    _push_direct "$label" "$url"
    return 0
  fi
  if _push_direct "$label" "$url" 2>/dev/null; then
    return 0
  fi
  if [[ "$allow_factory" -eq 1 ]]; then
    _push_via_factory "$label" "$url"
    return 0
  fi
  echo "  ✗ push failed for ${label}" >&2
  return 1
}

echo "Monorepo → Gitea (ordered: #1 primary, #2 mirror), branch=${BRANCH}"

_push_one "Gitea#1" "$GITEA1_URL" 1
_push_one "Gitea#2" "$GITEA2_URL" 0

if [[ "$DRY_RUN" -eq 0 ]]; then
  git fetch origin 2>/dev/null || true
  echo ""
  echo "Done. Both Giteas should now be at $(_local_head)."
fi
