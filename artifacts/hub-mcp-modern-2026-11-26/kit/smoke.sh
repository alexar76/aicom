#!/usr/bin/env bash
# smoke.sh NEW_TAG — the new image answers both protocol eras; no network, a throw-away database.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
docker run --rm --network none -v "$D/smoke_mcp.py:/tmp/smoke_mcp.py:ro" --entrypoint python "$1" /tmp/smoke_mcp.py 2>&1 | tail -2
