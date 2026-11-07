#!/bin/sh
# Daily tool-set digest cross-check with CrawlCheck, run by histor-xcheck-crawlcheck.timer on admin-vps (12:00 UTC).
# Source 1, always: CrawlCheck's public change feed. It holds the newest 500 events (about two and a half days) and
# cannot be paged, so the run is daily. Source 2, once CrawlCheck publishes it: the shared server list, at
# THEIRS_LIST_URL. Output: /var/lib/histor-datasets/xcheck-crawlcheck/<date>/, served by nginx as
# https://histor.modelmarket.dev/datasets/xcheck-crawlcheck/<date>/ (and latest/).
set -eu
FEED_URL=${FEED_URL:-https://crawlcheck.io/api/v1/mcp/changes?limit=500}
THEIRS_LIST_URL=${THEIRS_LIST_URL:-}
DAY=$(date -u +%F)
ROOT=/var/lib/histor-datasets/xcheck-crawlcheck
OUT=$ROOT/$DAY
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

one() {  # one <name> <url>: fetch, compare, keep the input beside the report
  curl -fsS --max-time 120 -A 'histor-xcheck/1 (+https://histor.modelmarket.dev/)' -o "$TMP/$1.input.json" "$2"
  status=0
  python3 /opt/histor-xcheck/xcheck_digests.py "$TMP/$1.input.json" --out "$TMP/$1.report.json" --md "$TMP/$1.report.md" \
    > /dev/null || status=$?
  [ "$status" -le 1 ] || exit "$status"   # 1 = at least one disagreement: still a result to publish
}

one feed "$FEED_URL"
if [ -n "$THEIRS_LIST_URL" ]; then one list "$THEIRS_LIST_URL"; fi

mkdir -p "$OUT"
cp "$TMP"/*.json "$TMP"/*.md "$OUT"/
(cd "$OUT" && sha256sum ./*.json ./*.md > SHA256SUMS)
ln -sfn "$DAY" "$ROOT/latest"
