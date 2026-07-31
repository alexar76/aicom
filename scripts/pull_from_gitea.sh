#!/usr/bin/env bash
# pull_from_gitea.sh — REVERSE of mirror_to_gitea.sh.
# Pull a component's own Gitea repo back INTO its monorepo folder, so edits made
# elsewhere (e.g. on the oracle server / server 2) flow into the local monorepo.
#
# SAFE BY DEFAULT: overlay mode — only adds/updates files, NEVER deletes local
# files. Use --delete ONLY when you are certain the Gitea remote is the source of
# truth and you want to remove local-only files to match the remote exactly.
#
# Targets come from scripts/gitea-targets.yaml (host/owner/repo); the destination
# folder is the matching satellites[].id path in scripts/satellite-map.yaml.
# It rsyncs the remote content into the local folder (git-tracked, so review with
# `git diff` and commit yourself — this does NOT commit).
#
# Usage:
#   ./scripts/pull_from_gitea.sh                   # all targets, overlay (safe)
#   ./scripts/pull_from_gitea.sh oracles platon    # specific components, overlay
#   ./scripts/pull_from_gitea.sh --delete          # MIRROR mode — deletes local-only!
#   ./scripts/pull_from_gitea.sh --list
#   ./scripts/pull_from_gitea.sh --dry-run oracles
#
# Auth: git credential helper (osxkeychain) or $GITEA_TOKEN.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${GITEA_BRANCH:-main}"
DRY_RUN=0
DO_LIST=0
DELETE=0                           # SAFE default: overlay (never delete local files)
COMPONENTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  DRY_RUN=1; shift ;;
    --list)     DO_LIST=1; shift ;;
    --delete)   DELETE=1; shift ;;  # explicit opt-in to mirror mode
    --branch)   BRANCH="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '2,18p' "$0"; exit 0 ;;
    --*)        echo "unknown option: $1" >&2; exit 1 ;;
    *)          COMPONENTS+=("$1"); shift ;;
  esac
done

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
    return {"url": f"{base.rstrip('/')}/{owner}/{repo}.git", "src": (src or "").rstrip("/"), "repo": repo}

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

_gitea_project_root_markers() {
  local d="$1"
  [[ -f "$d/package.json" || -f "$d/pyproject.toml" || -f "$d/Cargo.toml" || -f "$d/go.mod" ]] && return 0
  [[ -f "$d/README.md" && ( -d "$d/src" || -d "$d/lib" || -d "$d/tests" || -d "$d/test" ) ]] && return 0
  return 1
}

# Gitea repos are sometimes pushed with an extra top-level folder (e.g. dioscuri/dioscuri/).
# Detect that layout in the clone and rsync from the inner project root instead.
_gitea_resolve_clone_root() {
  local clone="$1" repo="$2" src="$3"
  if _gitea_project_root_markers "$clone"; then
    printf '%s\n' "$clone"
    return 0
  fi
  local name nested=""
  for name in "$repo" "$(basename "$src")" "$src"; do
    [[ -n "$name" && -d "$clone/$name" ]] || continue
    if _gitea_project_root_markers "$clone/$name"; then
      nested="$clone/$name"
      break
    fi
  done
  if [[ -n "$nested" ]]; then
    printf '%s\n' "$nested"
  else
    printf '%s\n' "$clone"
  fi
}

# If a previous pull already created component/nested/, hoist files up.
_gitea_remove_stray_nested_pull() {
  local dest="$1" repo="$2" src="$3"
  local name stray=""
  for name in "$repo" "$(basename "$src")"; do
    [[ -n "$name" && -d "$dest/$name" ]] || continue
    if _gitea_project_root_markers "$dest/$name"; then
      stray="$dest/$name"
      break
    fi
  done
  [[ -n "$stray" ]] || return 0
  echo "  ℹ️  hoisting stray ${stray#$dest/}/ into component root"
  rsync -a "$stray/" "$dest/"
  rm -rf "$stray"
}

if [[ "$DO_LIST" -eq 1 ]]; then
  echo "Configured Gitea targets (pull source → local folder):"
  for sid in $(_map list-ids); do
    URL=""; SRC=""; REPO=""
    eval "$(_map resolve "$sid")"
    printf "  %-24s %s  →  %s/\n" "$sid" "${URL:-<unresolved>}" "${SRC:-?}"
  done
  exit 0
fi

if [[ ${#COMPONENTS[@]} -eq 0 ]]; then
  while IFS= read -r _id; do [[ -n "$_id" ]] && COMPONENTS+=("$_id"); done < <(_map list-ids)
fi

WORKDIR=""
if [[ "$DRY_RUN" -eq 0 ]]; then
  WORKDIR="$(mktemp -d)"
  trap 'rm -rf "$WORKDIR"' EXIT
fi

pull_one() {
  local sid="$1"
  local URL="" SRC="" REPO=""
  eval "$(_map resolve "$sid")"
  if [[ -z "$URL" || -z "$SRC" ]]; then
    echo "  ⚠️  SKIP ${sid}: no resolvable gitea target/source"; return 1
  fi
  echo ""
  echo "━━━ ${sid}: ${URL}  →  ${SRC}/ ━━━"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would clone ${REPO} and rsync into ${SRC}/ ($([[ $DELETE -eq 1 ]] && echo 'mirror/--delete' || echo overlay))"
    return 0
  fi
  local clone="$WORKDIR/$REPO"
  if ! git_t clone --depth 1 --branch "$BRANCH" "$URL" "$clone" 2>/dev/null; then
    echo "  ⚠️  SKIP: cannot clone $URL (branch $BRANCH)"; return 1
  fi
  local source
  source="$(_gitea_resolve_clone_root "$clone" "$REPO" "$SRC")"
  if [[ "$source" != "$clone" ]]; then
    echo "  ℹ️  flattening nested Gitea layout: ${source#"$clone"/}/"
  fi
  mkdir -p "$ROOT/$SRC"
  local rsync_args=(-a)
  [[ "$DELETE" -eq 1 ]] && rsync_args+=(--delete)
  # Never touch local-only operational dirs / VCS metadata.
  for pat in .git .claude .cursor .venv venv node_modules __pycache__ \
             .pytest_cache .mypy_cache .dart_tool build dist .mesh_data \
             "*.egg-info" .DS_Store data; do
    rsync_args+=(--exclude "$pat")
  done
  rsync "${rsync_args[@]}" "$source/" "$ROOT/$SRC/"
  _gitea_remove_stray_nested_pull "$ROOT/$SRC" "$REPO" "$SRC"
  local changed
  changed="$(git -C "$ROOT" status --porcelain -- "$SRC" | wc -l | tr -d ' ')"
  echo "  ✓ synced — ${changed} path(s) changed in ${SRC}/ (review: git diff -- ${SRC})"
}

rc=0
for sid in "${COMPONENTS[@]}"; do
  pull_one "$sid" || rc=1
done
echo ""
echo "Done. Review with 'git status' / 'git diff', then commit + dual-push (git push origin main)."
exit "$rc"
