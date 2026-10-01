#!/usr/bin/env bash
# ============================================================================
# Reverse-import: bring merged PRs from a LIVE satellite back into the monorepo.
# ============================================================================
# For `history: live` satellites, contributors open PRs on GitHub. Once merged,
# those commits live on the satellite's main but NOT in the monorepo — the
# canonical source. Before the next outbound sync (mirror_satellites.sh) can run,
# the change must land in the monorepo, or the sync's rsync-overwrite would
# revert it (and its divergence guard will refuse to run until you do this).
#
# This script is READ-ONLY toward GitHub and NON-DESTRUCTIVE toward the monorepo:
# it clones the satellite, computes the delta since the last monorepo-sync commit
# (i.e. the merged PRs), strips the mirror-injected artifacts (governance, badge
# tooling, banner), and writes a reviewable PATCH. YOU review, apply, and commit.
# It never pushes and never auto-edits your working tree.
#
#   ./scripts/import_satellite_pr.sh metis
#
# Then:
#   git apply --directory=metis /tmp/aicom-import/metis.patch   # review first!
#   git -C . add metis && git commit -m "feat(metis): import PR #NN from GitHub"
#   ALLOW_DIVERGENCE=1 ./scripts/publish_all_repos.sh --satellite metis   # re-sync
# ============================================================================
set -euo pipefail

SAT_ID="${1:-}"
[[ -n "$SAT_ID" ]] || { echo "usage: $0 <satellite-id>   (e.g. metis)"; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
HOST="${SATELLITE_GITHUB_HOST:-github.com}"
BRANCH="${SATELLITE_BRANCH:-main}"
OUTDIR="${IMPORT_OUTDIR:-/tmp/aicom-import}"
SYNC_SUBJECT_PREFIX="chore(satellite): sync"

# ── Resolve repo, monorepo path, and history mode from the map ───────────────
read -r REPO MONO_PATH MODE < <(python3 - "$SAT_ID" <<PY
import sys, yaml
from pathlib import Path
sat = sys.argv[1]
m = yaml.safe_load(Path("${ROOT}/scripts/satellite-map.yaml").read_text(encoding="utf-8"))
for s in m.get("satellites") or []:
    if s.get("id") == sat:
        repo = s.get("repo") or sat
        layout = s.get("export_layout") or {}
        path = layout.get("root_from") or (s.get("paths") or [sat])[0]
        mode = str(s.get("history", "mirror")).strip().lower()
        print(repo, path, mode)
        break
else:
    print("", "", "")
PY
)

[[ -n "$REPO" ]] || { echo "✗ '$SAT_ID' not found in scripts/satellite-map.yaml"; exit 1; }
if [[ "$MODE" != "live" ]]; then
  echo "✗ '$SAT_ID' is history: ${MODE:-mirror}, not 'live'. Reverse-import only applies to live satellites."
  echo "  (mirror satellites are read-only — PRs there are overwritten, so there is nothing to import.)"
  exit 1
fi
[[ -d "$ROOT/$MONO_PATH" ]] || { echo "✗ monorepo path missing: $MONO_PATH"; exit 1; }

# ── Clone the satellite (read-only; token only if provided, for private repos) ─
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
if [[ -n "$TOKEN" ]]; then
  URL="https://x-access-token:${TOKEN}@${HOST}/${ORG}/${REPO}.git"
else
  URL="https://${HOST}/${ORG}/${REPO}.git"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "▶ Cloning ${ORG}/${REPO} (${BRANCH}) …"
git clone --quiet --branch "$BRANCH" "$URL" "$WORK/sat" || {
  echo "✗ clone failed (private repo? set GH_PAT). URL host: ${HOST}/${ORG}/${REPO}"
  exit 1
}

# ── Find the last monorepo-sync commit → everything after it is external work ─
cd "$WORK/sat"
BASE="$(git log --format='%H%x09%s' | awk -F'\t' -v p="$SYNC_SUBJECT_PREFIX" 'index($2,p)==1{print $1; exit}')"

if [[ -z "$BASE" ]]; then
  echo "⚠ No '${SYNC_SUBJECT_PREFIX} …' commit found in history — cannot locate a sync baseline."
  echo "  This repo may not have been synced in live mode yet. Nothing imported."
  exit 0
fi
if [[ "$BASE" == "$(git rev-parse HEAD)" ]]; then
  echo "✓ Satellite tip IS the last monorepo-sync commit — no external PRs to import."
  exit 0
fi

echo ""
echo "External commits since last sync ($(git rev-parse --short "$BASE")):"
git log --format='  %h  %an  %s' "${BASE}..HEAD"
echo ""

# ── Emit a reviewable patch, minus mirror-injected artifacts ─────────────────
mkdir -p "$OUTDIR"
PATCH="$OUTDIR/${SAT_ID}.patch"
git diff "${BASE}..HEAD" -- . \
  ':(exclude)LICENSE' ':(exclude)SECURITY.md' ':(exclude)CONTRIBUTING.md' \
  ':(exclude)CODE_OF_CONDUCT.md' ':(exclude)CONTRIBUTORS.md' \
  ':(exclude).github' ':(exclude)docs/badges' \
  ':(exclude)scripts/ci_static_badge.sh' ':(exclude)scripts/generate_static_badge.py' \
  ':(exclude)scripts/satellite-map.yaml' \
  > "$PATCH" || true

if [[ ! -s "$PATCH" ]]; then
  echo "✓ External commits touch only mirror-injected files (governance/badges) — nothing to import into the monorepo."
  exit 0
fi

echo "✅ Wrote reviewable patch: $PATCH ($(wc -l < "$PATCH") lines)"
echo ""
echo "Next (all local — nothing is pushed):"
echo "  1. Review:  \$EDITOR $PATCH   (drop any README mirror-banner hunk if present)"
echo "  2. Apply:   git -C \"$ROOT\" apply --directory=$MONO_PATH \"$PATCH\""
echo "  3. Commit:  git -C \"$ROOT\" add $MONO_PATH && git -C \"$ROOT\" commit -m \"feat($SAT_ID): import PR from GitHub\""
echo "  4. Re-sync: ALLOW_DIVERGENCE=1 ./scripts/publish_all_repos.sh --satellite $SAT_ID   (you run the push)"
