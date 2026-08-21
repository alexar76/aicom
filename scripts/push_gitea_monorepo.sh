#!/usr/bin/env bash
# push_gitea_monorepo.sh — push the aicom monorepo to Gitea#2 only:
#   Gitea#2  alexar76/aicom  (ssh://git@gitea2) — sole monorepo mirror
#
# Gitea#1 (Superowner/aicom) is retired from this pipeline.
#
# Auth: SSH via Host gitea2 (~/.ssh/config ProxyJump), or GITEA_TOKEN where applicable.
#
# Usage:
#   ./scripts/push_gitea_monorepo.sh              # push current branch (default main)
#   ./scripts/push_gitea_monorepo.sh --dry-run    # show remote + pending commits
#   GITEA_BRANCH=main ./scripts/push_gitea_monorepo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GITEA_BRANCH:-main}"
DRY_RUN=0
GITEA2_URL="ssh://git@gitea2/alexar76/aicom.git"

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

# Same AI/bot trailer rules as satellite mirrors + factory snapshot
# (scripts/sanitize_git_commit_meta.py). School and every other path share one
# gate: Cursor/Claude/Copilot/github-actions Co-authored-by must not land on
# newly pushed Gitea commits. Human Co-authored-by (aicom-coauthors.txt) stays.
#
# Default: scan only the unpushed range (remote..HEAD). If Gitea is unreachable,
# fall back to HEAD tip only — never scan all of main (old history may predate
# the sanitizer). Override: SKIP_TRAILER_GATE=1
_assert_clean_commit_trailers() {
  local url="$1"
  if [[ "${SKIP_TRAILER_GATE:-0}" == "1" ]]; then
    echo "  ⚠️  SKIP_TRAILER_GATE=1 — not scanning AI/bot Co-authored-by trailers"
    return 0
  fi
  local remote_sha range
  remote_sha="$(_remote_head "$url" || true)"
  if [[ -n "$remote_sha" ]]; then
    range="${remote_sha}..${BRANCH}"
  else
    echo "  ⚠️  could not reach remote for trailer scan — checking HEAD tip only"
    range="${BRANCH}^!"
  fi

  # Empty range (already up to date) — nothing to scan
  if ! git rev-list --max-count=1 "$range" >/dev/null 2>&1; then
    echo "  ✓ AI/bot Co-authored-by gate: nothing to scan"
    return 0
  fi

  local dirty gate_rc=0
  dirty="$(
    python3 - "$ROOT/scripts/sanitize_git_commit_meta.py" "$range" <<'PY'
import subprocess, sys
from pathlib import Path

san = Path(sys.argv[1])
rev_range = sys.argv[2]
try:
    shas = subprocess.check_output(
        ["git", "rev-list", rev_range], text=True, stderr=subprocess.DEVNULL
    ).split()
except subprocess.CalledProcessError:
    raise SystemExit(0)
bad = []
for sha in shas:
    body = subprocess.check_output(
        ["git", "log", "-1", "--format=%B", sha], text=True
    )
    clean = subprocess.check_output(
        [sys.executable, str(san)], input=body, text=True
    )
    if body.replace("\r\n", "\n").rstrip("\n") != clean.replace("\r\n", "\n").rstrip("\n"):
        bad.append(sha[:12])
if bad:
    print(" ".join(bad[:40]))
    if len(bad) > 40:
        print(f"...and {len(bad) - 40} more", file=sys.stderr)
    raise SystemExit(2)
PY
  )" && gate_rc=0 || gate_rc=$?

  if [[ "$gate_rc" -ne 0 ]]; then
    echo "ERROR: unpushed commit(s) still carry AI/bot trailers (same strip as school satellite mirrors):" >&2
    echo "  ${dirty:-<see above>}" >&2
    echo "  Fix tip:  git log -1 --format=%B | python3 scripts/sanitize_git_commit_meta.py > /tmp/msg && git commit --amend -F /tmp/msg" >&2
    echo "  Emergency only: SKIP_TRAILER_GATE=1" >&2
    exit 1
  fi
  echo "  ✓ AI/bot Co-authored-by gate clean (sanitize_git_commit_meta.py — same as school + other satellites)"
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
  _assert_clean_commit_trailers "$url"
  git_t push "$url" "${BRANCH}:${BRANCH}"
  remote="$(_remote_head "$url" || true)"
  if [[ "$remote" != "$local_head" ]]; then
    echo "  ✗ push reported OK but remote still at ${remote:-<unknown>}" >&2
    return 1
  fi
  echo "  ✓ pushed → ${label}"
}

echo "Monorepo → Gitea#2 only (alexar76/aicom), branch=${BRANCH}"

_push_direct "Gitea#2" "$GITEA2_URL"

if [[ "$DRY_RUN" -eq 0 ]]; then
  git fetch origin 2>/dev/null || true
  echo ""
  echo "Done. Gitea#2 should now be at $(_local_head)."
fi
