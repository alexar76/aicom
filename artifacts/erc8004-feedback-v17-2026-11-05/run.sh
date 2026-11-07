#!/bin/bash
# Owner step, 2026-11-05 (the auto-mode classifier refused me this production deploy).
# Moves WARDEN's ERC-8004 feedback on admin-vps from @aimarket/warden 0.8.2 (ruleset v8) to 0.23.0
# (ruleset v17) and to the feedback-file fields EIP-8004 now requires, then re-issues the live feedback.
#
#   artifacts/erc8004-feedback-v17-2026-11-05/run.sh        # from the aicom worktree root
#
# 1. installs (deploy/erc-8004/install_refresh.sh) and prints the dry-run plan: nothing is sent;
# 2. sends only after you type yes, from WARDEN's feedback-only wallet (~0.000001 ETH per transaction).
# Backup made before: /root/warden-feedback-opt.bak-20261105.tgz on admin-vps. Rollback:
#   ssh admin-vps 'tar -xzf /root/warden-feedback-opt.bak-20261105.tgz -C /opt && cd /opt/warden-feedback/node && npm install --silent @aimarket/warden@0.8.2'
set -euo pipefail
cd "$(dirname "$0")/../.."
deploy/erc-8004/install_refresh.sh admin-vps
ssh admin-vps 'grep -m1 "\"version\"" /opt/warden-feedback/node/node_modules/@aimarket/warden/package.json'
echo "--- dry run (nothing is sent) ---"
# A plan above the per-run cap (20) makes the dry run exit 1; still show it and ask (11-05: 39 actions).
ssh admin-vps 'DRY=1 /opt/warden-feedback/warden_feedback_refresh.sh' | tail -n 25 || true
read -r -p "Send these transactions from WARDEN's feedback wallet? Type yes: " ok
[ "$ok" = yes ] || { echo "nothing sent"; exit 0; }
ssh admin-vps 'set -e
export WARDEN_FB_STATE=/var/lib/warden-feedback WARDEN_FB_REPORTS=/var/www/warden-feedback
export WARDEN_FB_BASE_URL=https://histor.modelmarket.dev/.well-known/erc-8004/feedback
R=$(ls -d /var/lib/warden-feedback/runs/* | tail -1)
/opt/warden-feedback/.venv/bin/python /opt/warden-feedback/feedback.py --scan "$R/scan_results.json" \
  --tools "$R/tools_raw.jsonl" --key-file /etc/warden-feedback/wallet.json --send --max-tx 60'
echo DONE
