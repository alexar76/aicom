#!/usr/bin/env bash
# Deploy Pantheon (pantheon.modelmarket.dev) — thin wrapper around pantheon/scripts/deploy.sh.
#
#   ./scripts/deploy_pantheon.sh --remote root@competing-lab \
#     --identity ~/.ssh/id_ed25519_factory [--install-nginx] [--issue-cert]
#
# Gitea monorepo only (pantheon/ is stripped from the public GitHub factory).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/pantheon/scripts/deploy.sh" "$@"
