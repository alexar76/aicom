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

redact_remote() {
  local url="$1"
  if [[ "$url" =~ ^https?://[^/@]+@[^/]+ ]]; then
    echo "$url" | sed -E 's#(https?://)[^:@/]+:[^@]+@#\1***:***@#'
  else
    echo "$url"
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

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

TARGET="$WORKDIR/factory"
if [[ -n "$EXPORT_DIR" ]]; then
  TARGET="$EXPORT_DIR"
  mkdir -p "$TARGET"
  rsync -a --delete "${RSYNC_EXCLUDE_ARGS[@]}" "$ROOT/" "$TARGET/"
  echo "OK exported factory tree → $TARGET"
  exit 0
fi

if [[ -z "$REMOTE" ]]; then
  echo "error: set --remote or AICOM_FACTORY_REMOTE or configure git origin" >&2
  exit 2
fi

echo "Cloning $(redact_remote "$REMOTE") (branch $BRANCH) …"
git clone --depth 1 --branch "$BRANCH" "$REMOTE" "$WORKDIR/clone" 2>/dev/null || {
  git clone --depth 1 "$REMOTE" "$WORKDIR/clone"
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
for p in .claude .cursor; do
  rm -rf "$CLONE/$p"
done

cd "$CLONE"
git add -A

# Force-remove excluded paths from git index
for p in "${EXCLUDES[@]}"; do
  git rm -rf --ignore-unmatch "$p" 2>/dev/null || true
done
git rm -rf --ignore-unmatch data/state .claude .cursor 2>/dev/null || true

if git diff --cached --quiet && git diff --quiet; then
  echo "Nothing to commit — factory remote already matches trimmed tree."
  exit 0
fi

MSG="${COMMIT_MSG:-chore(factory): sync trimmed aicom without satellite subtrees}"
git commit -m "$MSG"

if [[ "$NO_PUSH" -eq 1 ]]; then
  echo "OK committed in $CLONE (not pushed)"
  echo "Review: cd $CLONE && git log -1 --stat"
  trap - EXIT
  echo "Temp clone kept at $CLONE (not deleted due to --no-push)"
  exit 0
fi

echo "Pushing to $(redact_remote "$REMOTE") ($BRANCH) …"
git push origin "HEAD:$BRANCH"
echo "OK factory remote updated — satellite folders removed from $(redact_remote "$REMOTE")"
