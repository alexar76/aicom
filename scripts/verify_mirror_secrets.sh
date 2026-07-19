#!/usr/bin/env bash
# Fail before push if a satellite mirror tree contains secrets or runtime config.
set -euo pipefail

clone="${1:-}"
[[ -n "$clone" && -d "$clone" ]] || {
  echo "usage: verify_mirror_secrets.sh <clone-dir>" >&2
  exit 2
}

fail=0

for forbidden in .env .env.local .env.production dioscuri.config.json argus.config.json helios.config.yaml client_secret.json youtube_token.json; do
  if [[ -f "$clone/$forbidden" ]]; then
    echo "error: forbidden file in mirror: $forbidden" >&2
    fail=1
  fi
done

# Runtime secret files inside data/ (directory itself may exist e.g. alien-monitor fixtures).
if [[ -f "$clone/data/.env" ]] || find "$clone/data" -name '.env' -print -quit 2>/dev/null | grep -q .; then
  echo "error: .env under data/ must not be mirrored" >&2
  fail=1
fi

# Obvious token shapes — empty assignments in .env.example are fine (not present here).
if rg -q -i \
  '(npm_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[a-zA-Z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})' \
  "$clone" 2>/dev/null; then
  echo "error: suspected API token literal in mirror tree" >&2
  fail=1
fi

# Stray satellite pollution — another repo's tree must never ship inside a mirror.
if [[ "$(basename "$clone")" == "dioscuri" ]]; then
  for stray_file in main.py config.yaml pipeline_worker.py; do
    if [[ -f "$clone/$stray_file" ]]; then
      echo "error: stray factory file in dioscuri mirror: $stray_file" >&2
      fail=1
    fi
  done
  for stray in acex web agents ai-service-mesh aimarket-hub alien-monitor argus lottery oracles platon plugins ecosystem-landing dioscuri contracts; do
    if [[ -d "$clone/$stray" ]]; then
      echo "error: stray $stray/ inside dioscuri mirror" >&2
      fail=1
    fi
  done
  if [[ -f "$clone/scripts/mirror_satellites.sh" || -f "$clone/scripts/publish_all_repos.sh" ]]; then
    echo "error: factory publish scripts must not be mirrored into dioscuri" >&2
    fail=1
  fi
fi

if find "$clone" -path '*/broadcast/*.json' -print -quit 2>/dev/null | grep -q .; then
  echo "error: Foundry broadcast artifacts must not be mirrored" >&2
  fail=1
fi

# SQLite runtime artifacts (including accidental :memory: files from connect(":memory:") bugs).
for junk in ":memory:" ":memory:-wal" ":memory:-shm"; do
  if [[ -e "$clone/$junk" ]]; then
    echo "error: SQLite runtime artifact in mirror: $junk" >&2
    fail=1
  fi
done
if find "$clone" -maxdepth 3 \( -name '*.sqlite3' -o -name '*.sqlite3-wal' -o -name '*.sqlite3-shm' \) -print -quit 2>/dev/null | grep -q .; then
  echo "error: SQLite database files must not be mirrored" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "OK mirror secrets check: $(basename "$clone")"
