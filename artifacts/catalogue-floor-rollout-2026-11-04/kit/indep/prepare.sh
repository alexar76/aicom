#!/usr/bin/env bash
# prepare.sh — Independent (venv): check the live files, back them up, build a patched COPY of the package and run
# the smoke on it under the venv's Python. Touches nothing the service uses.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
V=/opt/independentai/venvs/hub-3.16.0-rpc-security-20261031
P="$(ls -d $V/lib/python3*/site-packages/aimarket_hub)"
while read -r sha f; do
  live="$(sha256sum "$P/$f" | cut -c1-12)"
  [[ "$live" == "$sha" ]] || { echo "$f live $live, context patched from $sha — stop"; exit 1; }
done < "$D/live.sha"
mkdir -p "$D/backup-venv"
for f in crawler.py database.py migrations.py cli.py; do cp -p "$P/$f" "$D/backup-venv/$f"; done
rm -rf "$D/pkg"; mkdir -p "$D/pkg"; cp -a "$P" "$D/pkg/aimarket_hub"
for f in crawler.py database.py migrations.py cli.py; do cp "$D/$f" "$D/pkg/aimarket_hub/$f"; done
find "$D/pkg" -name __pycache__ -prune -exec rm -rf {} +
T="$(mktemp -d)"; cd "$T"
env -i PATH=/usr/bin:/bin HOME="$T" PYTHONPATH="$D/pkg" SMOKE_EXPECT_PKG="$D/pkg/aimarket_hub/" \
  "$V/bin/python" "$D/smoke.py" 2>&1 | grep -v 'signing key generated' | tail -1
rm -rf "$T"
echo "venv package $P"
