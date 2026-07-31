#!/usr/bin/env bash
# mirror_to_gitea.sh — export component folders from this monorepo to their own
# Gitea repos. Host/target config lives in scripts/gitea-targets.yaml (internal
# infra, excluded from the public GitHub mirror); component source folders come
# from scripts/satellite-map.yaml. Gitea counterpart of mirror_satellites.sh,
# fully independent of it — the GitHub flow is untouched.
#
# Usage:
#   ./scripts/mirror_to_gitea.sh                 # all configured targets
#   ./scripts/mirror_to_gitea.sh oracles         # one component by satellite id
#   ./scripts/mirror_to_gitea.sh --list          # show configured targets
#   ./scripts/mirror_to_gitea.sh --dry-run       # preview only, no changes
#   ./scripts/mirror_to_gitea.sh --no-push       # commit in temp clone, don't push
#
# Auth: uses your git credential helper (osxkeychain — same as `origin`).
#       For CI/headless, set GITEA_TOKEN (sent as `Authorization: token <...>`).
# Note: the factory itself (repo root) already pushes to Gitea via `origin`;
#       this script handles the peer subfolders only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GITEA_BRANCH:-main}"
DRY_RUN=0
NO_PUSH=0
SINGLE=""
DO_LIST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-push) NO_PUSH=1; shift ;;
    --branch)  BRANCH="${2:-}"; shift 2 ;;
    --list)    DO_LIST=1; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    --*)       echo "unknown option: $1" >&2; exit 1 ;;
    *)         SINGLE="$1"; shift ;;
  esac
done

# ── satellite-map.yaml readers ───────────────────────────────────────────────
_map() {
  python3 - "$@" <<'PY'
import sys, shlex, yaml
from pathlib import Path

m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text()) or {}
g = yaml.safe_load(Path("scripts/gitea-targets.yaml").read_text()) or {}
hosts = g.get("hosts") or {}
targets = g.get("targets") or {}
sats = {s["id"]: s for s in (m.get("satellites") or [])}

def resolve(sid):
    t = targets.get(sid)
    if not isinstance(t, dict):
        return None
    base = hosts.get(t.get("host"))
    owner, repo = t.get("owner"), t.get("repo")
    if not (base and owner and repo):
        return None
    src = None
    for p in (sats.get(sid, {}).get("paths") or []):
        if isinstance(p, str) and p != ".":
            src = p.split(":", 1)[1] if p.startswith("plugins:") else p
            break
    return {
        "url": f"{base.rstrip('/')}/{owner}/{repo}.git",
        "src": (src or "").rstrip("/"),
        "repo": repo,
    }

cmd = sys.argv[1]
if cmd == "list-ids":
    for sid in targets:
        print(sid)
elif cmd == "resolve":
    r = resolve(sys.argv[2])
    if r:
        print(f"URL={shlex.quote(r['url'])}")
        print(f"SRC={shlex.quote(r['src'])}")
        print(f"REPO={shlex.quote(r['repo'])}")
PY
}

git_t() {
  if [[ -n "${GITEA_TOKEN:-}" ]]; then
    git -c http.extraHeader="Authorization: token ${GITEA_TOKEN}" "$@"
  else
    git "$@"
  fi
}

if [[ "$DO_LIST" -eq 1 ]]; then
  echo "Configured Gitea targets (scripts/satellite-map.yaml → gitea_targets):"
  for sid in $(_map list-ids); do
    URL=""; SRC=""; REPO=""
    eval "$(_map resolve "$sid")"
    printf "  %-24s %-10s → %s\n" "$sid" "${SRC:-?}" "${URL:-<unresolved>}"
  done
  exit 0
fi

WORKDIR=""
if [[ "$DRY_RUN" -eq 0 ]]; then
  WORKDIR="$(mktemp -d)"
  trap 'rm -rf "$WORKDIR"' EXIT
fi

# Hoist landing/ for static site roots (parity with mirror_satellites GitHub Pages).
_gitea_post_rsync() {
  local sid="$1"
  local clone="$2"
  case "$sid" in
    theoros|dioscuri|helios)
      if [[ -f "$clone/landing/index.html" ]]; then
        cp "$clone/landing/index.html" "$clone/index.html"
        if [[ -f "$clone/landing/.nojekyll" ]]; then
          cp "$clone/landing/.nojekyll" "$clone/.nojekyll"
        else
          : > "$clone/.nojekyll"
        fi
        echo "  ✓ landing/index.html → index.html (static site root)"
      fi
      ;;
    metis)
      if [[ -f "$clone/docs/landing/index.html" ]]; then
        cp "$clone/docs/landing/index.html" "$clone/index.html"
        : > "$clone/.nojekyll"
        echo "  ✓ docs/landing/index.html → index.html (static site root)"
      fi
      ;;
  esac
}

mirror_one() {
  local sid="$1"
  if [[ "$sid" == "course" ]]; then
    sid="aimarket-courses"
  fi
  local URL="" SRC="" REPO=""
  eval "$(_map resolve "$sid")"
  if [[ -z "$URL" || -z "$SRC" ]]; then
    echo "  ⚠️  SKIP ${sid}: no resolvable gitea target/host/source"; return 1
  fi
  echo ""
  echo "━━━ ${sid} → ${URL}  (folder: ${SRC}) ━━━"
  if [[ ! -d "$ROOT/$SRC" ]]; then
    echo "  ⚠️  SKIP: source folder missing: $SRC"; return 1
  fi
  if [[ "$sid" == course* ]] && [[ -f "$ROOT/$SRC/scripts/build_course_assets.py" ]]; then
    echo "  Building course site + Colab notebooks …"
    python3 "$ROOT/$SRC/scripts/build_course_assets.py"
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would sync ${SRC}/ → ${REPO} (${URL})"; return 0
  fi

  local API_BASE="" GITEA_OWNER=""
  API_BASE="$(python3 - "$URL" <<'PY'
import sys, urllib.parse
u = urllib.parse.urlsplit(sys.argv[1])
print(f"{u.scheme}://{u.netloc}")
PY
)"
  GITEA_OWNER="$(python3 - "$URL" <<'PY'
import sys, urllib.parse
parts = urllib.parse.urlsplit(sys.argv[1]).path.strip("/").split("/")
print(parts[0] if parts else "")
PY
)"
  if ! git_t ls-remote "$URL" &>/dev/null 2>&1; then
    echo "  ℹ️  remote missing — ensuring Gitea repo ${GITEA_OWNER}/${REPO} exists …"
    python3 "$ROOT/scripts/gitea_ensure_repo.py" "$API_BASE" "$GITEA_OWNER" "$REPO" || {
      echo "  ⚠️  could not create repo — create ${GITEA_OWNER}/${REPO} in Gitea UI or set GITEA_TOKEN" >&2
      return 1
    }
  fi

  local clone="$WORKDIR/$REPO"
  if git_t ls-remote "$URL" "refs/heads/$BRANCH" &>/dev/null; then
    git_t clone --depth 1 --branch "$BRANCH" "$URL" "$clone" 2>/dev/null || {
      git_t clone --depth 1 "$URL" "$clone"
      ( cd "$clone" && { git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"; } )
    }
  else
    mkdir -p "$clone"
    ( cd "$clone" && git init -q && git checkout -q -b "$BRANCH" && git remote add origin "$URL" )
    echo "  ℹ️  remote empty/new — initialized fresh"
  fi

  # Wipe tracked content (keep .git), then resync from the monorepo folder.
  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a)
  for pat in .git .claude .cursor .venv venv node_modules __pycache__ \
             .pytest_cache .mypy_cache .dart_tool build dist .mesh_data \
             "*.egg-info" .DS_Store .env "data/secrets" "*.key" "*.enc" \
             "*.sqlite3" "*.sqlite3-*" "*.sqlite" "*.db"; do
    rsync_args+=(--exclude "$pat")
  done
  rsync "${rsync_args[@]}" "$ROOT/$SRC/" "$clone/"

  _gitea_post_rsync "$sid" "$clone"

  ( cd "$clone"
    git add -A
    if git diff --cached --quiet; then
      echo "  ✓ up to date — nothing to push"; exit 0
    fi
    git -c user.name="${GIT_AUTHOR_NAME:-aicom-mirror}" \
        -c user.email="${GIT_AUTHOR_EMAIL:-mirror@aicom.local}" \
        commit -q -m "${GITEA_COMMIT_MSG:-chore(mirror): sync ${sid} from monorepo}"
    if [[ "$NO_PUSH" -eq 1 ]]; then
      echo "  ✓ committed (not pushed): $clone"; exit 0
    fi
    git_t push origin "HEAD:$BRANCH" && echo "  ✓ pushed → ${REPO}"
  )
}

if [[ -n "$SINGLE" ]]; then
  mirror_one "$SINGLE"
else
  ids="$(_map list-ids)"
  if [[ -z "$ids" ]]; then
    echo "No gitea_targets configured in scripts/satellite-map.yaml"; exit 0
  fi
  rc=0
  for sid in $ids; do
    mirror_one "$sid" || rc=1
  done
  exit "$rc"
fi
