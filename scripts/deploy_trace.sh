#!/usr/bin/env bash
# Deploy the Pantheon installation at trace.modelmarket.dev (Gitea monorepo).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/pantheon/scripts/deploy-trace.sh" "$@"
