#!/bin/sh
# Deploy the gateway to the apex host: ./deploy.sh [ssh-target]
#
# Ships the committed sources (not the working tree of other services), builds there and swaps
# the container with a health check and automatic rollback (deploy/remote.sh). The apex nginx
# routes /a2mcp and /x402/ to 127.0.0.1:9485 (deploy/nginx/modelmarket.dev.conf).
set -eu
TARGET="${1:-root@80.209.243.27}"
KEY="${OKX_A2MCP_SSH_KEY:-$HOME/.ssh/id_ed25519_factory}"
PAY_TO="${X402_PAY_TO:-0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a}"   # the operator wallet: public
cd "$(dirname "$0")"
TAG="prod-$(date -u +%Y%m%d)-$(git rev-parse --short HEAD)"
if [ -n "$(git status --porcelain -- . )" ]; then echo "okx-a2mcp has uncommitted changes; commit first" >&2; exit 1; fi
rsync -az --delete -e "ssh -i $KEY -o IdentitiesOnly=yes" \
  Dockerfile package.json package-lock.json src deploy/remote.sh "$TARGET:/opt/okx-a2mcp/"
# One short command per ssh: long heredoc scripts have hung on this host before.
ssh -i "$KEY" -o IdentitiesOnly=yes "$TARGET" "sh /opt/okx-a2mcp/remote.sh $TAG $PAY_TO" < /dev/null
