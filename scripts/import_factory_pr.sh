#!/usr/bin/env bash
# ============================================================================
# Reverse-import: bring merged PRs from GitHub alexar76/aicom into the monorepo.
# ============================================================================
# Factory GitHub is history: live (same as metis). Contributors open PRs there.
# Once merged, those commits live on GitHub main but NOT in the monorepo.
# Before the next outbound sync (publish_aicom_factory.sh) can run, the change
# must land here, or the sync's rsync would revert it (and the divergence
# guard refuses to run until you do this).
#
# READ-ONLY toward GitHub, NON-DESTRUCTIVE toward the monorepo: clones the
# factory remote, diffs since the last factory-sync commit, strips
# publish-injected artifacts (live README banner, factory .github copies,
# unpublished-stripped satellite-map), and writes a reviewable PATCH.
# YOU review, apply, and commit. Never pushes, never auto-edits the tree.
#
#   ./scripts/import_factory_pr.sh
#
# Then:
#   git apply /tmp/aicom-import/factory.patch   # review first!
#   git add <paths> && git commit -m "feat: import PR #NN from GitHub aicom"
#   ALLOW_DIVERGENCE=1 ./scripts/publish_aicom_factory.sh
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
HOST="${SATELLITE_GITHUB_HOST:-github.com}"
BRANCH="${AICOM_FACTORY_BRANCH:-main}"
REPO="aicom"
OUTDIR="${IMPORT_OUTDIR:-/tmp/aicom-import}"
SYNC_SUBJECT_PREFIX="chore(factory): sync"
# First live publish appends on top of the old snapshot commit; treat it as baseline too.
SNAPSHOT_SUBJECT_PREFIX="aicom — AI-Factory monorepo (public mirror, single-commit snapshot)"

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
  echo "✗ clone failed (set GH_PAT). URL host: ${HOST}/${ORG}/${REPO}"
  exit 1
}

cd "$WORK/sat"
BASE="$(git log --format='%H%x09%s' | awk -F'\t' -v p="$SYNC_SUBJECT_PREFIX" 'index($2,p)==1{print $1; exit}')"
if [[ -z "$BASE" ]]; then
  BASE="$(git log --format='%H%x09%s' | awk -F'\t' -v p="$SNAPSHOT_SUBJECT_PREFIX" 'index($2,p)==1{print $1; exit}')"
fi

if [[ -z "$BASE" ]]; then
  echo "⚠ No '${SYNC_SUBJECT_PREFIX} …' (or legacy snapshot) commit found — cannot locate a sync baseline."
  echo "  This repo may not have been published in live mode yet. Nothing imported."
  exit 0
fi
if [[ "$BASE" == "$(git rev-parse HEAD)" ]]; then
  echo "✓ Factory tip IS the last monorepo-sync commit — no external PRs to import."
  exit 0
fi

echo ""
echo "External commits since last sync ($(git rev-parse --short "$BASE")):"
git log --format='  %h  %an  %s' "${BASE}..HEAD"
echo ""

mkdir -p "$OUTDIR"
PATCH="$OUTDIR/factory.patch"
# Factory GitHub is a trimmed tree at repo root. Keep CONTRIBUTING / CONTRIBUTORS
# (those are canonical factory files). Drop publish-injected artifacts.
git diff "${BASE}..HEAD" -- . \
  ':(exclude).github' \
  ':(exclude)scripts/satellite-map.yaml' \
  ':(exclude)docs/badges' \
  ':(exclude)scripts/ci_static_badge.sh' \
  ':(exclude)scripts/generate_static_badge.py' \
  > "$PATCH" || true

if [[ ! -s "$PATCH" ]]; then
  echo "✓ External commits touch only publish-injected files — nothing to import into the monorepo."
  exit 0
fi

echo "✅ Wrote reviewable patch: $PATCH ($(wc -l < "$PATCH") lines)"
echo ""
echo "Next (all local — nothing is pushed):"
echo "  1. Review:  \$EDITOR $PATCH   (drop any README live-banner hunk if present)"
echo "  2. Apply:   git -C \"$ROOT\" apply \"$PATCH\""
echo "  3. Commit:  git -C \"$ROOT\" add <paths> && git -C \"$ROOT\" commit -m \"feat: import PR from GitHub aicom\""
echo "  4. Re-sync: ALLOW_DIVERGENCE=1 ./scripts/publish_aicom_factory.sh"
