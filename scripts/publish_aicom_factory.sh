#!/usr/bin/env bash
# Publish trimmed AI-Factory (aicom) tree to remote — WITHOUT satellite subtrees.
#
# Satellites (separate repos): acex, ai-service-mesh, aimarket-hub, aimarket-widget,
# aimarket-protocol, aimarket-sdks, aimarket-agent, desktop-integrations, pulse-terminal,
# plugins — see scripts/satellite-map.yaml
#
# Usage:
#   ./scripts/publish_aicom_factory.sh --dry-run
#   AICOM_FACTORY_REMOTE=git@github.com:alexar76/aicom.git ./scripts/publish_aicom_factory.sh
#   ./scripts/publish_aicom_factory.sh --export-dir /tmp/aicom-factory-export
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
NO_PUSH=0
BRANCH="${AICOM_FACTORY_BRANCH:-main}"
REMOTE="${AICOM_FACTORY_REMOTE:-}"
EXPORT_DIR=""
COMMIT_MSG=""

usage() {
  cat <<'EOF'
publish_aicom_factory.sh — push factory-only aicom (exclude satellite folders)

Options:
  --dry-run              Show excludes and rsync plan only
  --no-push              Commit locally in temp clone but do not push
  --remote URL           Factory git remote (default: origin or AICOM_FACTORY_REMOTE)
  --branch NAME          Target branch (default: main)
  --export-dir PATH      Write export to PATH instead of pushing
  --message TEXT         Commit message
  -h, --help             This help

Excluded paths are read from scripts/satellite-map.yaml (factory exclude + satellites).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-push) NO_PUSH=1; shift ;;
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --export-dir) EXPORT_DIR="${2:-}"; shift 2 ;;
    --message) COMMIT_MSG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$REMOTE" ]]; then
  REMOTE="$(git remote get-url origin 2>/dev/null || true)"
fi

TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
if [[ -z "$TOKEN" && "$REMOTE" =~ https://[^:/]+:([^@]+)@ ]]; then
  TOKEN="${BASH_REMATCH[1]}"
fi
if [[ -n "$TOKEN" && "$REMOTE" =~ github\.com[:/]+([^/]+/[^/.]+)(\.git)? ]]; then
  REMOTE="https://x-access-token:${TOKEN}@github.com/${BASH_REMATCH[1]}.git"
fi

# ── SAFETY GUARD ───────────────────────────────────────────────────────────
# This script force-pushes a TRIMMED, SINGLE-COMMIT, history-less snapshot to
# $REMOTE. If $REMOTE ever resolved to the canonical monorepo (origin / Gitea),
# that push would OVERWRITE it and destroy all history + satellites. $REMOTE
# falls back to `git remote get-url origin` when unset — and here origin is
# Gitea — so refuse anything that is not the public GitHub factory remote.
_remote_display="${REMOTE#*@}"   # strip any user:token@ prefix before showing
if [[ -z "$REMOTE" ]]; then
  echo "ERROR: no publish target." >&2
  echo "  Set AICOM_FACTORY_REMOTE=https://github.com/<org>/aicom.git (or pass --remote)." >&2
  exit 1
fi
if [[ "$REMOTE" != *github.com/* && "$REMOTE" != *github.com:* ]]; then
  echo "ERROR: refusing to publish — target is NOT a GitHub remote:" >&2
  echo "         ${_remote_display}" >&2
  echo "  This publishes a trimmed single-commit snapshot with --force. Pointing it" >&2
  echo "  at origin/Gitea would OVERWRITE the canonical monorepo and wipe its history." >&2
  echo "  Set AICOM_FACTORY_REMOTE=https://github.com/<org>/aicom.git (or pass --remote)." >&2
  exit 1
fi
if [[ ! "$REMOTE" =~ github\.com[:/]+[^/]+/aicom(\.git)?/?$ ]]; then
  echo "ERROR: refusing to publish — GitHub target is not a '<org>/aicom' repo:" >&2
  echo "         ${_remote_display}" >&2
  echo "  The factory snapshot must go to the aicom repo. Fix AICOM_FACTORY_REMOTE." >&2
  exit 1
fi
# ───────────────────────────────────────────────────────────────────────────

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

redact_remote() {
  local url="$1"
  if [[ "$url" =~ ^https?://[^/@]+@[^/]+ ]]; then
    echo "$url" | sed -E 's#(https?://)[^:@/]+:[^@]+@#\1***:***@#'
  else
    echo "$url"
  fi
}

# Factory remote excludes all of .github/ from rsync; restore public CI + community files.
# Prefer trimmed workflows under .github/workflows/factory/ (satellites absent on GitHub mirror).
copy_factory_github_assets() {
  local target="$1"
  local wf src
  mkdir -p "$target/.github/workflows"

  # Factory-specific CI / Security (required for green badges on trimmed tree).
  for pair in "ci.yml:ci.yml" "security-scan.yml:security-scan.yml"; do
    local from="${pair%%:*}"
    local to="${pair##*:}"
    src="$ROOT/.github/workflows/factory/$from"
    if [[ ! -f "$src" ]]; then
      src="$ROOT/.github/workflows/$to"
    fi
    if [[ -f "$src" ]]; then
      cp -f "$src" "$target/.github/workflows/$to"
    fi
  done

  # Ecosystem Pages workflow is shared.
  if [[ -f "$ROOT/.github/workflows/pages-ecosystem.yml" ]]; then
    cp -f "$ROOT/.github/workflows/pages-ecosystem.yml" \
      "$target/.github/workflows/pages-ecosystem.yml"
  fi

  if [[ -d "$ROOT/.github/ISSUE_TEMPLATE" ]]; then
    mkdir -p "$target/.github/ISSUE_TEMPLATE"
    cp -R "$ROOT/.github/ISSUE_TEMPLATE/." "$target/.github/ISSUE_TEMPLATE/"
  fi
  if [[ -f "$ROOT/.github/pull_request_template.md" ]]; then
    mkdir -p "$target/.github"
    cp -f "$ROOT/.github/pull_request_template.md" "$target/.github/pull_request_template.md"
  fi
}

# .cursor/ is rsync-excluded (local IDE junk), but shared project rules must ship.
copy_factory_cursor_rules() {
  local target="$1"
  if [[ -d "$ROOT/.cursor/rules" ]]; then
    mkdir -p "$target/.cursor/rules"
    # Only *.mdc project rules — never copy plans/chats/cache.
    find "$ROOT/.cursor/rules" -maxdepth 1 -type f -name '*.mdc' -exec cp -f {} "$target/.cursor/rules/" \;
  fi
}

EXCLUDES=()
while IFS= read -r line; do EXCLUDES+=("$line"); done < <(python3 "$ROOT/scripts/aicom_publish_config.py" list-excludes)
RSYNC_EXCLUDE_ARGS=()
while IFS= read -r line; do RSYNC_EXCLUDE_ARGS+=("$line"); done < <(python3 "$ROOT/scripts/aicom_publish_config.py" rsync-args)

echo "== AI-Factory publish (satellite paths excluded) =="
echo "Source:  $ROOT"
echo "Remote:  $(redact_remote "${REMOTE:-<none>}")"
echo "Branch:  $BRANCH"
echo ""
echo "Excluded from factory push:"
for p in "${EXCLUDES[@]}"; do
  echo "  - $p/"
done
echo ""

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] rsync args: ${RSYNC_EXCLUDE_ARGS[*]}"
  exit 0
fi

# Scan the trimmed publish tree (not the full monorepo — satellites + docs FPs).
# Paths match .github/workflows/factory/security-scan.yml.
run_factory_gitleaks() {
  local tree="$1"
  if ! command -v gitleaks >/dev/null 2>&1; then
    if [[ "${ALLOW_PUBLISH_WITHOUT_GITLEAKS:-}" == "1" ]]; then
      echo "warn: gitleaks not installed locally — proceeding due to ALLOW_PUBLISH_WITHOUT_GITLEAKS=1"
      echo "      (CI security-scan.yml secret-scan job still gates the published remote)"
      return 0
    fi
    echo "error: gitleaks not installed locally — refusing to publish without a pre-publish secret scan." >&2
    echo "       Install gitleaks (https://github.com/gitleaks/gitleaks) or set" >&2
    echo "       ALLOW_PUBLISH_WITHOUT_GITLEAKS=1 to override (CI security-scan.yml still gates)." >&2
    return 3
  fi
  echo "Running gitleaks on trimmed factory tree …"
  local stage
  stage="$(mktemp -d)"
  for p in security web/backend web/frontend/src scripts core llm orchestrator agents; do
    if [[ -e "$tree/$p" ]]; then
      mkdir -p "$stage/$(dirname "$p")"
      cp -a "$tree/$p" "$stage/$p"
    fi
  done
  gitleaks detect --source "$stage" --redact --no-git --exit-code 1
  rm -rf "$stage"
}

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

TARGET="$WORKDIR/factory"
if [[ -n "$EXPORT_DIR" ]]; then
  TARGET="$EXPORT_DIR"
  mkdir -p "$TARGET"
  rsync -a --delete "${RSYNC_EXCLUDE_ARGS[@]}" "$ROOT/" "$TARGET/"
  copy_factory_github_assets "$TARGET"
  copy_factory_cursor_rules "$TARGET"
  run_factory_gitleaks "$TARGET"
  echo "OK exported factory tree → $TARGET"
  exit 0
fi

if [[ -z "$REMOTE" ]]; then
  echo "error: set --remote or AICOM_FACTORY_REMOTE or configure git origin" >&2
  exit 2
fi

echo "Cloning $(redact_remote "$REMOTE") (branch $BRANCH) …"
git_auth clone --depth 1 --branch "$BRANCH" "$REMOTE" "$WORKDIR/clone" 2>/dev/null || {
  git_auth clone --depth 1 "$REMOTE" "$WORKDIR/clone"
  cd "$WORKDIR/clone"
  git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
  cd "$ROOT"
}

CLONE="$WORKDIR/clone"

echo "Syncing factory files (deleting satellite dirs on remote) …"
rsync -a --delete "${RSYNC_EXCLUDE_ARGS[@]}" "$ROOT/" "$CLONE/"

# Ensure satellite directories are removed even if rsync missed edge cases
for p in "${EXCLUDES[@]}"; do
  if [[ -e "$CLONE/$p" ]]; then
    rm -rf "$CLONE/$p"
  fi
done

# Runtime pipeline state must never ship to public factory remote
if [[ -e "$CLONE/data/state" ]]; then
  rm -rf "$CLONE/data/state"
fi

# rsync --exclude does not delete these from an existing remote clone
LOCAL_EXCLUDES=()
while IFS= read -r line; do LOCAL_EXCLUDES+=("$line"); done < <(python3 "$ROOT/scripts/aicom_publish_config.py" list-local-excludes)
for p in "${LOCAL_EXCLUDES[@]}"; do
  rm -rf "$CLONE/$p"
done

cd "$CLONE"
git add -A

# Force-remove excluded paths from git index
for p in "${EXCLUDES[@]}"; do
  git rm -rf --ignore-unmatch "$p" 2>/dev/null || true
done
for p in "${LOCAL_EXCLUDES[@]}"; do
  git rm -rf --ignore-unmatch "$p" 2>/dev/null || true
done
git rm -rf --ignore-unmatch data/state 2>/dev/null || true

copy_factory_github_assets "$CLONE"
copy_factory_cursor_rules "$CLONE"
run_factory_gitleaks "$CLONE"
for wf in pages-ecosystem.yml ci.yml security-scan.yml; do
  [[ -f "$CLONE/.github/workflows/$wf" ]] && git add ".github/workflows/$wf"
done
[[ -d "$CLONE/.github/ISSUE_TEMPLATE" ]] && git add ".github/ISSUE_TEMPLATE/"
[[ -f "$CLONE/.github/pull_request_template.md" ]] && git add ".github/pull_request_template.md"

if git diff --cached --quiet && git diff --quiet; then
  echo "Nothing to commit — factory remote already matches trimmed tree."
  exit 0
fi

MSG="${COMMIT_MSG:-aicom — AI-Factory monorepo (public mirror, single-commit snapshot)}"

# Credit external human contributors as co-authors of the snapshot commit so they
# appear in the GitHub contributor graph (the mirror has no accumulated history,
# so a Co-authored-by trailer on the single commit is the only durable credit).
# Curated, humans-only list — see scripts/aicom-coauthors.txt.
COAUTHORS_FILE="${ROOT}/scripts/aicom-coauthors.txt"
if [[ -f "$COAUTHORS_FILE" ]]; then
  _coauthor_block=""
  while IFS= read -r _ca; do
    _ca="${_ca%%#*}"                       # drop trailing/inline comments
    _ca="${_ca#"${_ca%%[![:space:]]*}"}"   # ltrim
    _ca="${_ca%"${_ca##*[![:space:]]}"}"   # rtrim
    [[ -z "$_ca" ]] && continue
    _coauthor_block+="Co-authored-by: ${_ca}"$'\n'
  done < "$COAUTHORS_FILE"
  if [[ -n "$_coauthor_block" ]]; then
    MSG="${MSG}"$'\n\n'"${_coauthor_block%$'\n'}"
    echo "Crediting co-authors from $(basename "$COAUTHORS_FILE"):"
    printf '%s\n' "$_coauthor_block" | sed 's/^/  /'
  fi
fi

# Publish as a SINGLE-COMMIT snapshot. The public factory mirror carries NO
# accumulated git history: we drop the cloned .git, re-init a fresh repo from the
# trimmed working tree, and force-push. This keeps the private monorepo's commit
# history (and anything ever removed in earlier commits) off the public GitHub
# remote. The no-op check above already exited when the tree was unchanged, so we
# only reach here when there is something new to publish.
rm -rf "$CLONE/.git"
git init -q -b "$BRANCH" "$CLONE"
cd "$CLONE"
git add -A
git -c user.name="AI Factory" -c user.email="factory@users.noreply.github.com" \
  commit -q -m "$MSG"

if [[ "$NO_PUSH" -eq 1 ]]; then
  echo "OK committed (squashed single commit) in $CLONE (not pushed)"
  echo "Review: cd $CLONE && git log -1 --stat"
  trap - EXIT
  echo "Temp clone kept at $CLONE (not deleted due to --no-push)"
  exit 0
fi

echo "Force-pushing single-commit snapshot to $(redact_remote "$REMOTE") ($BRANCH) …"
git_auth push --force "$REMOTE" "HEAD:$BRANCH"
echo "OK factory remote updated as single-commit mirror (no history) — satellites excluded"
